# Copyright 2025 ApeCloud, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
from dataclasses import dataclass
from typing import Callable, List, Optional

from aperag.docparser.base import Part


def rechunk(
    parts: list[Part], chunk_size: int, chunk_overlap: int, tokenizer: Callable[[str], List[int]]
) -> list[Part]:
    rechunker = Rechunker(chunk_size, chunk_overlap, tokenizer)
    return rechunker(parts)


@dataclass
class Group:
    title_level: int
    title: str
    items: list[Part]
    tokens: int | None = None


class Rechunker:
    def __init__(self, chunk_size: int, chunk_overlap: int, tokenizer: Callable[[str], List[int]]):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.tokenizer = tokenizer

    def __call__(self, parts: list[Part]) -> list[Part]:
        groups = self._to_groups(parts)
        groups = self._merge_consecutive_title_groups(groups)
        return self._rechunk(groups)

    def _is_pure_title_group(self, group: Group) -> bool:
        """A group is considered a pure title if it has a title and only one item."""
        return group.title_level > 0 and len(group.items) == 1

    def _merge_consecutive_title_groups(self, groups: list[Group]) -> list[Group]:
        if not groups:
            return []

        new_groups: list[Group] = []
        i = 0
        while i < len(groups):
            current_group = groups[i]

            if not self._is_pure_title_group(current_group):
                new_groups.append(current_group)
                i += 1
                continue

            # It's a pure title group, let's look ahead to merge.
            merged_items = list(current_group.items)
            # The highest level is the smallest number.
            highest_level = current_group.title_level

            j = i + 1
            # 1. Merge consecutive pure title groups
            while j < len(groups):
                next_group = groups[j]
                if not self._is_pure_title_group(next_group):
                    break  # Stop merging titles

                # Check hierarchy: don't merge a higher-level title (e.g., H2 into an H3 group)
                if next_group.title_level < highest_level:
                    break

                # Merge it
                merged_items.extend(next_group.items)
                j += 1

            # 2. After merging titles, try to merge one more content group
            if j < len(groups):
                next_group = groups[j]
                if not self._is_pure_title_group(next_group):
                    if next_group.title_level == 0 or next_group.title_level >= current_group.title_level:
                        merged_items.extend(next_group.items)
                        j += 1  # This content group is also merged

            # Create the new merged group
            # The title and title_level of the merged group should be from the first group.
            new_group = Group(
                title_level=current_group.title_level,
                title=current_group.title,
                items=merged_items,
            )
            new_groups.append(new_group)
            i = j  # Move index to the next un-processed group

        return new_groups

    def _to_groups(self, parts: list[Part]) -> list[Group]:
        result: list[Group] = []
        curr_group: Group | None = None

        for part in parts:
            if not part.content:
                continue

            nesting = part.metadata.get("md_nesting", 0)
            title_level = 0
            title = ""
            if hasattr(part, "level"):  # TitlePart
                title_level = part.level
                title = part.content or ""

            if curr_group is None:
                curr_group = Group(title_level=title_level, title=title, items=[part])
                result.append(curr_group)
                continue

            # For simplicity, titles within lower-level nesting will not create new groups.
            if title_level == 0 or nesting != 0:
                curr_group.items.append(part)
                continue

            curr_group = Group(title_level=title_level, title=title, items=[part])
            result.append(curr_group)

        return result

    def _rechunk(self, groups: list[Group]) -> list[Part]:
        title_stack: list[tuple[str, int]] = []
        titles: list[str] = []
        result: list[Part] = []
        last_part: Part | None = None
        highest_level_in_last_part: int | None = None

        for group in groups:
            while len(title_stack) > 0 and title_stack[-1][1] >= group.title_level:
                title_stack.pop()
            if group.title_level > 0:
                title_stack.append((group.title, group.title_level))
            titles = [tup[0] for tup in title_stack]

            group_tokens = self._count_tokens(group)

            # Check if the group can be merged into the last Part
            can_merge = True
            if highest_level_in_last_part is not None and highest_level_in_last_part > group.title_level:
                # Do not merge if the current group has a higher title level
                # (e.g., merging content under a main heading into a sub-heading)
                can_merge = False
            last_part_tokens = 0 if last_part is None else self._count_tokens(last_part)
            if last_part_tokens + group_tokens > self.chunk_size:
                can_merge = False

            if can_merge:
                last_part = self._append_group_to_part(group, last_part, titles)
                if highest_level_in_last_part is None:
                    highest_level_in_last_part = group.title_level
                continue

            # Since the current group can't be merged into the last part,
            # the last part can be sealed.
            if last_part is not None:
                result.append(last_part)
                last_part = None
                highest_level_in_last_part = None

            # Split large parts
            parts: list[Part] = []
            for part in group.items:
                tokens = self._count_tokens(part)
                if tokens > self.chunk_size:
                    # If the single part is too large, split it into smaller chunks
                    splitter = SimpleSemanticSplitter(self.tokenizer)
                    chunks = splitter.split(part.content, self.chunk_size, self.chunk_overlap)
                    metadata = part.metadata.copy()
                    metadata.pop("tokens", None)
                    metadata["splitted"] = True
                    for chunk in chunks:
                        parts.append(Part(content=chunk, metadata=metadata.copy()))
                else:
                    parts.append(part)

            # Rechunk the parts
            assert last_part is None
            tokens_sum = 0
            prev_part_splitted = False
            for part in parts:
                curr_part_splitted = part.metadata.get("splitted", False)
                tokens = self._count_tokens(part)
                # Don't merge parts if too many tokens, or the previous part is splitted.
                if tokens_sum + tokens > self.chunk_size or (prev_part_splitted and not curr_part_splitted):
                    if last_part is not None:
                        result.append(last_part)
                        last_part = None
                        tokens_sum = 0

                last_part = self._append_part_to_part(part, last_part, titles)
                tokens_sum += tokens
                prev_part_splitted = curr_part_splitted

            # Don't merge any group into a partial group
            if last_part is not None:
                result.append(last_part)
                last_part = None
                highest_level_in_last_part = None

        if last_part is not None:
            result.append(last_part)

        return result

    def _append_group_to_part(self, group: Group, dest: Part | None, titles: list[str]) -> Part:
        for part in group.items:
            dest = self._append_part_to_part(part, dest, titles)
        return dest

    def _append_part_to_part(self, part: Part, dest: Part | None, titles: list[str]) -> Part:
        if dest is None:
            metadata = part.metadata.copy()
            if titles:
                metadata["titles"] = titles.copy()
            # Normalize to a Part
            return Part(content=part.content, metadata=metadata)
        dest.content += "\n\n" + part.content
        self._merge_md_source_map(dest, part)
        self._merge_pdf_source_map(dest, part)
        dest.metadata.pop("tokens", None)
        return dest

    def _merge_md_source_map(self, dest: Part, src: Part):
        dest_map = dest.metadata.get("md_source_map", None)
        src_map = src.metadata.get("md_source_map", None)
        if dest_map is None and src_map is None:
            return
        if dest_map is not None and src_map is None:
            return
        if dest_map is None and src_map is not None:
            dest.metadata["md_source_map"] = src_map
            return
        new_map = [min(dest_map[0], src_map[0]), max(dest_map[1], src_map[1])]
        dest.metadata["md_source_map"] = new_map

    def _merge_pdf_source_map(self, dest: Part, src: Part):
        dest_map: list[dict] = dest.metadata.get("pdf_source_map", None)
        src_map: list[dict] = src.metadata.get("pdf_source_map", None)
        if dest_map is None and src_map is None:
            return
        if dest_map is not None and src_map is None:
            return
        if dest_map is None and src_map is not None:
            dest.metadata["pdf_source_map"] = src_map
            return
        new_map = dest_map
        for item in src_map:
            if item not in new_map:
                new_map.append(item)
        dest.metadata["pdf_source_map"] = new_map

    def _count_tokens(self, elem: Group | Part) -> int:
        if isinstance(elem, Group):
            if elem.tokens is not None:
                return elem.tokens
            total = 0
            for child in elem.items:
                num = self._count_tokens(child)
                total += num
            elem.tokens = total
            return elem.tokens
        else:
            # elem is a Part
            tokens = elem.metadata.get("tokens", None)
            if tokens is not None:
                return tokens
            tokens = len(self.tokenizer(elem.content))
            elem.metadata["tokens"] = tokens
            return tokens


class SimpleSemanticSplitter:
    # List of separators used for splitting text into smaller chunks while preserving semantic coherence.
    # The separators are ordered hierarchically based on their impact on coherence.
    # Separators with less impact (e.g., paragraph breaks) are prioritized (appear earlier).
    # Separators with more impact (e.g., spaces) are used as a last resort (appear later).
    LEVELED_SEPARATORS = [
        ["\n\n"],
        ["\n"],
        ["。”", "！”", "？”"],
        ['."', '!"', '?"'],
        ["。", "！", "？"],
        [".", "!", "?"],
        ["；", "，", "、"],
        [";", ","],
        ["》", "）", "】", "」", "’", "”"],
        ["“", ">", ")", "]", "}", "'", '"'],
        [" ", "\t"],
    ]

    def __init__(self, tokenizer: Callable[[str], List[int]]):
        self.tokenizer = tokenizer

    def split(self, s: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        return self._recursive_split(s, chunk_size, chunk_overlap, 0)

    def _fit(self, s: str, chunk_size: int) -> bool:
        return len(self.tokenizer(s)) <= chunk_size

    def _recursive_split(self, s: str, chunk_size: int, chunk_overlap: int, level: int) -> list[str]:
        if len(s) == 0:
            return []
        if len(s) <= 1 or self._fit(s, chunk_size):
            return [s]

        # No more separators can guide semantic segmentation, so split arbitrarily.
        if level >= len(self.LEVELED_SEPARATORS):
            p = len(s) // 2
            left = self._recursive_split(s[:p], chunk_size, chunk_overlap, level + 1)
            overlap = ""
            if chunk_overlap > 0:
                # Extract a substring with size `chunk_overlap` from the right side of the left part (`s[:p]`)
                # to serve as `overlap`.
                # However, `overlap` cannot be equal to `s[:p]`, otherwise the algorithm won't converge.
                # Therefore, use the right half of `s[:p]` for splitting to ensure `overlap` is not equal to `s[:p]`.
                mid = p // 2
                if mid > 0:
                    overlap = self._cut_right_side(s[:p][mid:], chunk_overlap)
            right = self._recursive_split(overlap + s[p:], chunk_size, chunk_overlap, level + 1)
            return left + right

        chunks = [s]
        for sep in self.LEVELED_SEPARATORS[level]:
            new_chunks = []
            for chunk in chunks:
                parts = chunk.split(sep)
                new_chunks.extend([part + sep for part in parts[:-1]])
                new_chunks.append(parts[-1])
            chunks = new_chunks

        new_chunks = []
        for chunk in chunks:
            # If a chunk `chunk` is larger than `chunk_size`, it will be further split into smaller pieces;
            # otherwise, it remains unchanged.
            parts = self._recursive_split(chunk, chunk_size, chunk_overlap, level + 1)
            new_chunks.extend(parts)
        chunks = new_chunks

        # Merge small pieces into larger chunks, ensuring they fit within `chunk_size`.
        chunks = self._merge_small_chunks(chunks, chunk_size)

        return chunks

    def _cut_right_side(self, s: str, chunk_size: int) -> str:
        if len(s) == 0 or self._fit(s, chunk_size):
            return s
        if len(s) <= 1:
            return ""
        left = 0
        right = len(s)
        while left < right:
            mid = (left + right) // 2
            if self._fit(s[mid:], chunk_size):
                right = mid
            else:
                left = mid + 1
        return s[left:]

    def _merge_small_chunks(self, chunks: list[str], chunk_size: int) -> list[str]:
        merged_chunks = []
        current_chunk = ""
        for chunk in chunks:
            if len(current_chunk) == 0:
                current_chunk = chunk
                continue
            if self._fit(current_chunk + chunk, chunk_size):
                current_chunk += chunk
            else:
                merged_chunks.append(current_chunk)
                current_chunk = chunk
        if len(current_chunk) > 0:
            merged_chunks.append(current_chunk)
        return merged_chunks


class TextPreprocessor:
    """
    Text preprocessing utilities for cleaning document content before chunking.

    Usage:
        preprocessor = TextPreprocessor(
            collapse_whitespace=True, remove_urls_emails=True
        )
        cleaned = preprocessor.preprocess(raw_text)
    """

    URL_PATTERN = re.compile(r"https?://\S+")
    EMAIL_PATTERN = re.compile(r"[\w.\-+]+@[\w\-]+\.\w+")
    WHITESPACE_PATTERN = re.compile(r"\s+")

    def __init__(self, collapse_whitespace: bool = False, remove_urls_emails: bool = False):
        self.collapse_whitespace = collapse_whitespace
        self.remove_urls_emails = remove_urls_emails

    @property
    def enabled(self) -> bool:
        return self.collapse_whitespace or self.remove_urls_emails

    def preprocess(self, text: str) -> str:
        """Apply enabled preprocessing rules to the text."""
        if not text:
            return text
        if self.remove_urls_emails:
            text = self.URL_PATTERN.sub("", text)
            text = self.EMAIL_PATTERN.sub("", text)
        if self.collapse_whitespace:
            text = self.WHITESPACE_PATTERN.sub(" ", text)
        return text


class ParentChildRechunker:
    """
    Two-stage rechunker that produces parent-child chunk pairs.

    Supports two splitting modes:
    - Separator-based: Use custom delimiters to split parents (e.g. "##")
      and children (e.g. "\\n\\n").
    - Hierarchy-based: Use the standard Rechunker which respects document
      title hierarchy. Used when separators are empty.

    Text preprocessing (collapse whitespace, remove URLs/emails) is applied
    before chunking when enabled.

    At retrieval time, when a child chunk is matched, the full parent content
    is returned, giving the LLM rich surrounding context.

    Usage:
        rechunker = ParentChildRechunker(
            parent_chunk_size=800, child_chunk_size=150,
            child_chunk_overlap=50, tokenizer=my_tokenizer,
            parent_separator="##", child_separator="\\n\\n",
            preprocessor=TextPreprocessor(collapse_whitespace=True),
        )
        children = rechunker(parts)
    """

    def __init__(
        self,
        parent_chunk_size: int,
        child_chunk_size: int,
        child_chunk_overlap: int,
        tokenizer: Callable[[str], List[int]],
        parent_separator: Optional[str] = None,
        child_separator: Optional[str] = None,
        preprocessor: Optional[TextPreprocessor] = None,
    ):
        self.parent_chunk_size = parent_chunk_size
        self.child_chunk_size = child_chunk_size
        self.child_chunk_overlap = child_chunk_overlap
        self.tokenizer = tokenizer
        self.parent_separator = parent_separator or ""
        self.child_separator = child_separator or ""
        self.preprocessor = preprocessor

    def __call__(self, parts: list[Part]) -> list[Part]:
        """
        Produce child chunks whose metadata carries parent_content.

        Returns:
            list[Part]: child chunks ready for embedding, each with
                        metadata["parent_id"] and metadata["parent_content"].
        """
        if not parts:
            return []

        # Extract and preprocess raw text from parts
        raw_text = self._extract_raw_text(parts)
        if self.preprocessor and self.preprocessor.enabled:
            raw_text = self.preprocessor.preprocess(raw_text)

        # Stage 1: Create large parent chunks
        parent_chunks = self._create_parent_chunks(parts, raw_text)

        # Stage 2: Split each parent into child chunks
        all_children = self._create_child_chunks(parent_chunks)

        return all_children

    def _extract_raw_text(self, parts: list[Part]) -> str:
        """Concatenate all part content into a single raw text."""
        texts = []
        for part in parts:
            if part.content and part.content.strip():
                texts.append(part.content)
        return "\n\n".join(texts)

    def _create_parent_chunks(self, parts: list[Part], raw_text: str) -> list[Part]:
        """Create parent chunks, using separator or hierarchy-based splitting."""
        if self.parent_separator:
            return self._split_by_separator(raw_text, self.parent_separator,
                                            max_chunk_size=self.parent_chunk_size,
                                            chunk_overlap=max(self.parent_chunk_size // 10, 1),
                                            tokenizer=self.tokenizer, original_parts=parts)
        # Fallback to hierarchy-based Rechunker
        parent_rechunker = Rechunker(self.parent_chunk_size, max(self.parent_chunk_size // 10, 1), self.tokenizer)
        parent_parts = parent_rechunker._to_groups(parts)
        parent_parts = parent_rechunker._merge_consecutive_title_groups(parent_parts)
        return parent_rechunker._rechunk(parent_parts)

    def _create_child_chunks(self, parent_chunks: list[Part]) -> list[Part]:
        """Split each parent into child chunks."""
        all_children: list[Part] = []

        for parent_idx, parent_part in enumerate(parent_chunks):
            parent_content = parent_part.content or ""
            if not parent_content.strip():
                continue

            parent_id = f"parent_{parent_idx}"

            if self.child_separator:
                child_parts = self._split_by_separator(parent_content, self.child_separator,
                                                       max_chunk_size=self.child_chunk_size,
                                                       chunk_overlap=self.child_chunk_overlap,
                                                       tokenizer=self.tokenizer)
            else:
                child_rechunker = Rechunker(self.child_chunk_size, self.child_chunk_overlap, self.tokenizer)
                wrapper_parts = [Part(content=parent_content, metadata=parent_part.metadata.copy())]
                child_parts = child_rechunker._to_groups(wrapper_parts)
                child_parts = child_rechunker._merge_consecutive_title_groups(child_parts)
                child_parts = child_rechunker._rechunk(child_parts)

            for child in child_parts:
                if not child.content or not child.content.strip():
                    continue
                child.metadata["parent_id"] = parent_id
                child.metadata["parent_content"] = parent_content
                child.metadata["parent_chunk_size"] = self.parent_chunk_size
                child.metadata["child_chunk_size"] = self.child_chunk_size
                all_children.append(child)

        return all_children

    @staticmethod
    def _split_by_separator(text: str, separator: str, max_chunk_size: int = 0,
                            chunk_overlap: int = 0, tokenizer: Callable[[str], List[int]] = None,
                            original_parts: list[Part] = None) -> list[Part]:
        """
        Split text by separator into Part objects.

        Handles escaped newlines (\\n\\n → real newlines) in separators.
        Empty segments are skipped.
        If max_chunk_size > 0, oversized segments are further split via the
        standard Rechunker to stay within embedding model limits.
        """
        # Unescape common escape sequences in separators
        sep = separator.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")
        segments = text.split(sep)
        result = []
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            metadata = {}
            if original_parts:
                for part in original_parts:
                    if part.metadata:
                        metadata = part.metadata.copy()
                        break

            # If the segment is too large for the embedding model, further split it
            if max_chunk_size > 0 and tokenizer is not None and len(tokenizer(segment)) > max_chunk_size:
                sub_rechunker = Rechunker(max_chunk_size, chunk_overlap, tokenizer)
                wrapper = [Part(content=segment, metadata=metadata)]
                sub_groups = sub_rechunker._to_groups(wrapper)
                sub_groups = sub_rechunker._merge_consecutive_title_groups(sub_groups)
                sub_parts = sub_rechunker._rechunk(sub_groups)
                for sub_part in sub_parts:
                    if sub_part.content and sub_part.content.strip():
                        result.append(sub_part)
            else:
                result.append(Part(content=segment, metadata=metadata))
        return result
