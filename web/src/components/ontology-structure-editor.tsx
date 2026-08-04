'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import type { OwlPreview } from '@/lib/owl-mermaid';
import { useTranslations } from 'next-intl';
import { useMemo, useState } from 'react';
import { Plus, Trash2, X } from 'lucide-react';

export interface ClassNode {
  name: string;
  label?: string;
  comment?: string;
  parents?: string[];
}

export interface ObjPropNode {
  name: string;
  label?: string;
  comment?: string;
  domain?: string;
  range?: string;
  inverse?: string;
}

export interface DataPropNode {
  name: string;
  label?: string;
  comment?: string;
  range?: string;
  functional?: boolean;
}

const XSD_RANGES = ['string', 'integer', 'decimal', 'double', 'boolean', 'date', 'dateTime', 'anyURI'] as const;
const RANGE_LABEL_KEYS = {
  string: 'editor.range_string',
  integer: 'editor.range_integer',
  decimal: 'editor.range_decimal',
  double: 'editor.range_double',
  boolean: 'editor.range_boolean',
  date: 'editor.range_date',
  dateTime: 'editor.range_dateTime',
  anyURI: 'editor.range_anyURI',
} as const;

interface Props {
  structure: OwlPreview | null;
  onChange: (s: OwlPreview) => void;
}

/* Visual editor for the ontology structure: classes, relations and data properties.
   Every edit is committed through onChange so the parent can re-render the Mermaid
   graph in real time. */
export function OntologyStructureEditor({ structure, onChange }: Props) {
  const t = useTranslations('page_ontologies');
  const classes = useMemo(() => structure?.classes || [], [structure]);
  const objProps = useMemo(() => structure?.object_properties || [], [structure]);
  const dataProps = useMemo(() => structure?.data_properties || {}, [structure]);
  const [error, setError] = useState('');

  const emit = (next: OwlPreview) => {
    setError('');
    onChange(next);
  };

  const uniqueName = (base: string, taken: string[]) => {
    let name = base;
    let n = 2;
    while (taken.includes(name)) {
      name = `${base}${n}`;
      n++;
    }
    return name;
  };

  /* ---------- classes ---------- */

  const updateClass = (i: number, patch: Partial<ClassNode>) => {
    const next = [...classes];
    next[i] = { ...next[i], ...patch };
    emit({ ...structure!, classes: next });
  };

  const commitClassName = (i: number, value: string) => {
    const old = classes[i].name;
    const newName = value.trim();
    if (!newName || newName === old) {
      // revert in place
      const next = [...classes];
      next[i] = { ...next[i], name: old };
      emit({ ...structure!, classes: next });
      if (!newName) setError(t('editor.name_required'));
      return;
    }
    if (classes.some((c, j) => j !== i && c.name === newName)) {
      const next = [...classes];
      next[i] = { ...next[i], name: old };
      emit({ ...structure!, classes: next });
      setError(t('editor.class_name_exists'));
      return;
    }
    const next = [...classes];
    next[i] = { ...next[i], name: newName };
    const withClasses = { ...structure!, classes: next };
    // update references: parents lists, obj-prop domains/ranges, data-prop group keys
    withClasses.classes = next.map((c) => ({
      ...c,
      parents: (c.parents || []).map((p) => (p === old ? newName : p)),
    }));
    withClasses.object_properties = (withClasses.object_properties || []).map((p) => ({
      ...p,
      domain: p.domain === old ? newName : p.domain,
      range: p.range === old ? newName : p.range,
    }));
    if (withClasses.data_properties && old in withClasses.data_properties) {
      const { [old]: moved, ...rest } = withClasses.data_properties;
      withClasses.data_properties = { [newName]: moved, ...rest };
    }
    emit(withClasses);
  };

  const addClass = () => {
    const name = uniqueName(t('editor.default_class'), classes.map((c) => c.name));
    emit({ ...structure!, classes: [...classes, { name, label: name, parents: [] }] });
  };

  const removeClass = (i: number) => {
    const removed = classes[i].name;
    const withClasses: OwlPreview = {
      ...structure!,
      classes: classes.filter((_, j) => j !== i),
      object_properties: objProps.map((p) => ({
        ...p,
        domain: p.domain === removed ? undefined : p.domain,
        range: p.range === removed ? undefined : p.range,
      })),
      data_properties: Object.fromEntries(
        Object.entries(dataProps).filter(([k]) => k !== removed),
      ),
    };
    emit(withClasses);
  };

  const addParent = (i: number, parent: string) => {
    const current = classes[i].parents || [];
    if (current.includes(parent) || parent === classes[i].name) return;
    updateClass(i, { parents: [...current, parent] });
  };

  const removeParent = (i: number, parent: string) => {
    updateClass(i, { parents: (classes[i].parents || []).filter((p) => p !== parent) });
  };

  /* ---------- object properties ---------- */

  const updateObjProp = (i: number, patch: Partial<ObjPropNode>) => {
    const next = [...objProps];
    next[i] = { ...next[i], ...patch };
    emit({ ...structure!, object_properties: next });
  };

  const addObjProp = () => {
    const name = uniqueName(t('editor.default_relation'), objProps.map((p) => p.name));
    emit({ ...structure!, object_properties: [...objProps, { name, label: name, domain: '', range: '' }] });
  };

  const removeObjProp = (i: number) => {
    const removed = objProps[i].name;
    emit({
      ...structure!,
      object_properties: objProps.filter((_, j) => j !== i).map((p) => ({
        ...p,
        inverse: p.inverse === removed ? undefined : p.inverse,
      })),
    });
  };

  /* ---------- data properties ---------- */

  const updateDataProp = (cls: string, i: number, patch: Partial<DataPropNode>) => {
    const group = dataProps[cls] || [];
    const nextGroup = [...group];
    nextGroup[i] = { ...nextGroup[i], ...patch };
    emit({ ...structure!, data_properties: { ...dataProps, [cls]: nextGroup } });
  };

  const addDataProp = (cls: string) => {
    const group = dataProps[cls] || [];
    const name = uniqueName(t('editor.default_property'), Object.values(dataProps).flat().map((p) => p.name));
    emit({
      ...structure!,
      data_properties: { ...dataProps, [cls]: [...group, { name, label: name, range: 'string' }] },
    });
  };

  const removeDataProp = (cls: string, i: number) => {
    const group = dataProps[cls] || [];
    const next = { ...dataProps };
    if (group.length === 1) {
      delete next[cls];
    } else {
      next[cls] = group.filter((_, j) => j !== i);
    }
    emit({ ...structure!, data_properties: next });
  };

  const parentOptions = (exclude: string) => classes.filter((c) => c.name !== exclude).map((c) => c.name);
  const classOptions = classes.map((c) => c.name);

  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-3">
      {error && <p className="text-xs text-destructive">{error}</p>}

      {/* ---------- Classes ---------- */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">{t('editor.classes')} ({classes.length})</h3>
          <Button variant="outline" size="sm" onClick={addClass}>
            <Plus className="h-3 w-3 mr-1" /> {t('editor.add_class')}
          </Button>
        </div>
        {classes.length === 0 && <p className="text-xs text-muted-foreground">{t('editor.no_classes')}</p>}
        {classes.map((c, i) => (
          <div key={i} className="flex flex-col gap-2 rounded-md border p-2">
            <div className="flex items-center gap-2">
              <Input
                value={c.label || ''}
                placeholder={t('editor.label')}
                className="h-8 text-sm font-medium"
                onChange={(e) => updateClass(i, { label: e.currentTarget.value })}
              />
              <Input
                defaultValue={c.name}
                placeholder={t('editor.name')}
                className="h-8 text-sm font-mono"
                onBlur={(e) => commitClassName(i, e.currentTarget.value)}
              />
              <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive"
                onClick={() => removeClass(i)}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
            <Input
              value={c.comment || ''}
              placeholder={t('editor.comment')}
              className="h-7 text-xs"
              onChange={(e) => updateClass(i, { comment: e.currentTarget.value })}
            />
            <div className="flex flex-wrap items-center gap-1">
              {c.parents?.map((p) => (
                <Badge key={p} variant="secondary" className="gap-1 text-xs">
                  {p}
                  <button className="opacity-60 hover:opacity-100" onClick={() => removeParent(i, p)}>
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              ))}
              {parentOptions(c.name).length > 0 && (
                <Select onValueChange={(v) => addParent(i, v)}>
                  <SelectTrigger size="sm" className="h-6 text-xs px-2 gap-1">
                    <Plus className="h-3 w-3" />
                    <SelectValue placeholder={t('editor.add_parent')} />
                  </SelectTrigger>
                  <SelectContent>
                    {parentOptions(c.name).map((p) => (
                      <SelectItem key={p} value={p}>{p}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          </div>
        ))}
      </section>

      {/* ---------- Object properties ---------- */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">{t('editor.relations')} ({objProps.length})</h3>
          <Button variant="outline" size="sm" onClick={addObjProp}>
            <Plus className="h-3 w-3 mr-1" /> {t('editor.add_relation')}
          </Button>
        </div>
        {objProps.length === 0 && <p className="text-xs text-muted-foreground">{t('editor.no_relations')}</p>}
        {objProps.map((p, i) => (
          <div key={i} className="flex flex-col gap-2 rounded-md border p-2">
            <div className="flex items-center gap-2">
              <Input
                value={p.label || ''}
                placeholder={t('editor.label')}
                className="h-8 text-sm"
                onChange={(e) => updateObjProp(i, { label: e.currentTarget.value })}
              />
              <Input
                value={p.name}
                placeholder={t('editor.name')}
                className="h-8 text-sm font-mono"
                onChange={(e) => updateObjProp(i, { name: e.currentTarget.value })}
              />
              <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive"
                onClick={() => removeObjProp(i)}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <Select value={p.domain || ''} onValueChange={(v) => updateObjProp(i, { domain: v })}>
                <SelectTrigger size="sm" className="text-xs"><SelectValue placeholder={t('editor.domain')} /></SelectTrigger>
                <SelectContent>
                  {classOptions.map((n) => <SelectItem key={n} value={n}>{n}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={p.range || ''} onValueChange={(v) => updateObjProp(i, { range: v })}>
                <SelectTrigger size="sm" className="text-xs"><SelectValue placeholder={t('editor.range')} /></SelectTrigger>
                <SelectContent>
                  {classOptions.map((n) => <SelectItem key={n} value={n}>{n}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select
                value={p.inverse || ''}
                onValueChange={(v) => updateObjProp(i, { inverse: v || undefined })}
              >
                <SelectTrigger size="sm" className="text-xs"><SelectValue placeholder={t('editor.inverse')} /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="">{t('editor.none')}</SelectItem>
                  {objProps.filter((o) => o.name !== p.name).map((o) => (
                    <SelectItem key={o.name} value={o.name}>{o.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Input
              value={p.comment || ''}
              placeholder={t('editor.comment')}
              className="h-7 text-xs"
              onChange={(e) => updateObjProp(i, { comment: e.currentTarget.value })}
            />
          </div>
        ))}
      </section>

      {/* ---------- Data properties ---------- */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">
            {t('editor.properties')} ({Object.values(dataProps).reduce((s, v) => s + v.length, 0)})
          </h3>
          <Select onValueChange={(v) => addDataProp(v)}>
            <SelectTrigger size="sm" className="h-8 text-xs">
              <Plus className="h-3 w-3 mr-1" />
              <SelectValue placeholder={t('editor.add_property')} />
            </SelectTrigger>
            <SelectContent>
              {classOptions.map((n) => <SelectItem key={n} value={n}>{n}</SelectItem>)}
              <SelectItem value="*">{t('editor.global')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {Object.keys(dataProps).length === 0 && <p className="text-xs text-muted-foreground">{t('editor.no_properties')}</p>}
        {Object.entries(dataProps).map(([cls, props]) => (
          <div key={cls} className="space-y-1">
            <h4 className="text-xs font-medium text-muted-foreground">
              {cls === '*' ? t('editor.global') : cls}
            </h4>
            {props.map((dp, i) => (
              <div key={i} className="flex items-center gap-2 rounded-md border px-2 py-1.5">
                <Input
                  value={dp.label || ''}
                  placeholder={t('editor.label')}
                  className="h-7 text-sm"
                  onChange={(e) => updateDataProp(cls, i, { label: e.currentTarget.value })}
                />
                <Input
                  value={dp.name}
                  placeholder={t('editor.name')}
                  className="h-7 text-xs font-mono w-36"
                  onChange={(e) => updateDataProp(cls, i, { name: e.currentTarget.value })}
                />
                <Select value={dp.range || 'string'} onValueChange={(v) => updateDataProp(cls, i, { range: v })}>
                  <SelectTrigger size="sm" className="h-7 text-xs w-28"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {XSD_RANGES.map((r) => (
                      <SelectItem key={r} value={r}>{t(RANGE_LABEL_KEYS[r])}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <label className="flex items-center gap-1 text-xs text-muted-foreground whitespace-nowrap">
                  <Checkbox
                    checked={!!dp.functional}
                    onCheckedChange={(v) => updateDataProp(cls, i, { functional: !!v })}
                  />
                  {t('editor.functional')}
                </label>
                <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive"
                  onClick={() => removeDataProp(cls, i)}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        ))}
      </section>
    </div>
  );
}
