基于 OWL 2 官方规范和相关文档，以下是 OWL 本体语言所有核心构造的完整清单，按功能分类整理。

### 🏗️ 类 (Classes)
| 构造              | 说明                 |
| :---------------- | :------------------- |
| `owl:Class`       | 定义类               |
| `owl:Thing`       | 顶级类，包含所有个体 |
| `owl:Nothing`     | 空类                 |
| `owl:Restriction` | 属性限制类           |

### 🔗 对象属性 (Object Properties)
| 构造                       | 说明                     |
| :------------------------- | :----------------------- |
| `owl:ObjectProperty`       | 定义对象属性             |
| `owl:topObjectProperty`    | 连接所有个体的对象属性   |
| `owl:bottomObjectProperty` | 不连接任何个体的对象属性 |
| `owl:inverseOf`            | 定义属性的逆关系         |

### 📊 数据属性 (Data Properties)
| 构造                     | 说明                               |
| :----------------------- | :--------------------------------- |
| `owl:DatatypeProperty`   | 定义数据属性                       |
| `owl:topDataProperty`    | 连接所有个体与所有数据值的数据属性 |
| `owl:bottomDataProperty` | 不连接任何个体与数据值的数据属性   |

### 🏷️ 注解属性 (Annotation Properties)
| 构造                         | 说明                 |
| :--------------------------- | :------------------- |
| `owl:AnnotationProperty`     | 定义注解属性         |
| `rdfs:label`                 | 提供人类可读的名称   |
| `rdfs:comment`               | 提供描述性注释       |
| `rdfs:seeAlso`               | 提供额外资源链接     |
| `rdfs:isDefinedBy`           | 指出定义来源         |
| `owl:versionInfo`            | 提供版本信息         |
| `owl:deprecated`             | 标记已废弃的实体     |
| `owl:priorVersion`           | 指向前一个版本的本体 |
| `owl:backwardCompatibleWith` | 指示与旧版本兼容     |
| `owl:incompatibleWith`       | 指示与旧版本不兼容   |
| `owl:imports`                | 用于导入其他本体     |

### 🧩 属性特征 (Property Characteristics)
| 构造                            | 说明                           |
| :------------------------------ | :----------------------------- |
| `owl:FunctionalProperty`        | 函数属性（每个个体最多一个值） |
| `owl:InverseFunctionalProperty` | 逆函数属性                     |
| `owl:TransitiveProperty`        | 传递属性                       |
| `owl:SymmetricProperty`         | 对称属性                       |
| `owl:AsymmetricProperty`        | 非对称属性                     |
| `owl:ReflexiveProperty`         | 自反属性                       |
| `owl:IrreflexiveProperty`       | 非自反属性                     |

### 📐 类表达式构造器 (Class Expression Constructors)
| 构造                 | 说明                     |
| :------------------- | :----------------------- |
| `owl:intersectionOf` | 类交集                   |
| `owl:unionOf`        | 类并集                   |
| `owl:complementOf`   | 类补集                   |
| `owl:oneOf`          | 枚举类                   |
| `owl:someValuesFrom` | 存在量词（至少有一个值） |
| `owl:allValuesFrom`  | 全称量词（所有值都是）   |
| `owl:hasValue`       | 指定某个具体值           |
| `owl:minCardinality` | 最小基数                 |
| `owl:maxCardinality` | 最大基数                 |
| `owl:cardinality`    | 精确基数                 |
| `owl:hasSelf`        | 自反限制（OWL 2）        |

### 📜 公理 (Axioms)
| 构造                       | 说明                   |
| :------------------------- | :--------------------- |
| `rdfs:subClassOf`          | 子类公理               |
| `owl:equivalentClass`      | 等价类                 |
| `owl:disjointWith`         | 类不相交               |
| `owl:disjointUnionOf`      | 不相交并集             |
| `rdfs:subPropertyOf`       | 子属性                 |
| `owl:equivalentProperty`   | 等价属性               |
| `owl:propertyDisjointWith` | 属性不相交             |
| `owl:hasKey`               | 键约束（OWL 2）        |
| `owl:propertyChainAxiom`   | 属性链（OWL 2）        |
| `owl:sameAs`               | 个体相等               |
| `owl:differentFrom`        | 个体不等               |
| `owl:AllDifferent`         | 集合中所有个体两两不同 |

### 🧑‍🤝‍🧑 个体与断言 (Individuals and Assertions)
| 构造                                  | 说明               |
| :------------------------------------ | :----------------- |
| `owl:NamedIndividual`                 | 命名个体           |
| `owl:ClassAssertion`                  | 声明个体属于某个类 |
| `owl:ObjectPropertyAssertion`         | 声明对象属性断言   |
| `owl:DataPropertyAssertion`           | 声明数据属性断言   |
| `owl:NegativeObjectPropertyAssertion` | 否定对象属性断言   |
| `owl:NegativeDataPropertyAssertion`   | 否定数据属性断言   |

### 🧮 数据类型与数据范围 (Datatypes and Data Ranges)
| 构造                       | 说明                                                         |
| :------------------------- | :----------------------------------------------------------- |
| `rdfs:Datatype`            | RDF 数据类型类                                               |
| `owl:DataRange`            | 数据范围（OWL 1 中定义，已在 OWL 2 中弃用，建议使用 `rdfs:Datatype`） |
| `owl:datatypeComplementOf` | 数据范围补集                                                 |
| `owl:withRestrictions`     | 数据类型约束（如 `xsd:minInclusive`）                        |
