# Planner 稳定性测试报告

- 模型数：10
- 部件级测试数：20，成功：11，失败：9
- 总耗时：1272.61s
- planner：http://127.0.0.1:18085/v1

## Snowman（snowman）

部件：top hat, carrot nose, scarf

### 部件：top hat（30.31s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：top hat
- source_noun：snowman

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | tall cylindrical brimmed hat | uppermost segment with cylindrical crown | which concrete cross-domain entities exhibit this same relational property? | 0.92 |
| attr_02 | selected_part_function | head covering and festive silhouette | brim wider than head | which concrete cross-domain entities exhibit this same relational property? | 0.92 |
| attr_03 | attachment_logic | rests on the head sphere | attachment | which concrete cross-domain entities exhibit this same relational property? | 0.92 |
| attr_04 | orientation | vertical alignment | uppermost segment with cylindrical crown | which concrete cross-domain entities exhibit this same relational property? | 0.92 |
| attr_05 | articulation | non-articulated fixed form | brim wider than head | which concrete cross-domain entities exhibit this same relational property? | 0.92 |
| attr_06 | interface | flat surface interface | brim wider than head | which concrete cross-domain entities exhibit this same relational property? | 0.92 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（8 条）
- [near] `cylindrical hat` — Preserves the cylindrical shape and brimmed feature of the hat.
- [far] `cylindrical headgear` — Retains the cylindrical shape while searching for cross-domain entities.
- [near] `head resting object` — Preserves the attachment logic of resting on the head.
- [far] `head supported object` — Retains the attachment logic while searching for cross-domain entities.
- [near] `flat surface object` — Preserves the flat surface interface of the hat.
- [far] `flat interface object` — Retains the flat surface interface while searching for cross-domain entities.
- [near] `festive head covering` — Preserves the festive and head-covering function of the hat.
- [far] `ornamental headgear` — Retains the festive and decorative function while searching for cross-domain entities.

**getty_aat**（6 条）
- [near] `festive head covering` — Preserves the festive and head-covering function of the hat.
- [far] `ornamental headgear` — Retains the festive and decorative function while searching for cross-domain entities.
- [near] `fixed form object` — Preserves the non-articulated and fixed form of the hat.
- [far] `non-articulated structure` — Retains the non-articulated form while searching for cross-domain entities.
- [near] `cylindrical brimmed headgear` — Preserves the cylindrical shape and brimmed feature of the hat.
- [far] `brimmed cylindrical headgear` — Retains the cylindrical shape and brimmed feature while searching for cross-domain entities.

**asknature**（4 条）
- [near] `vertically aligned structure` — Preserves the vertical orientation of the hat.
- [far] `upright structure` — Retains the vertical orientation while searching for cross-domain entities.
- [near] `head resting object` — Preserves the attachment logic of resting on the head.
- [far] `head supported object` — Retains the attachment logic while searching for cross-domain entities.

### 部件：carrot nose（29.77s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：carrot nose
- source_noun：snowman

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | tapered orange cone protruding forward | forward-pointing cone at face center | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_02 | selected_part_function | nose landmark of the face | contrasting thin shape | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_03 | attachment_logic | inserted in the lower front of the head sphere | inserted in the lower front of the head sphere | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_04 | orientation | forward-pointing | forward-pointing cone at face center | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_05 | articulation | static | no movement or flexibility observed | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_06 | interface | smooth surface | no visible seams or joints | which concrete cross-domain entities exhibit this same relational property? | 0.9 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（8 条）
- [near] `tapered cone` — Preserves the tapered shape and forward protrusion of the cone.
- [far] `forward-pointing cone` — Focuses on the directional property of the cone while omitting the source noun.
- [near] `inserted head component` — Preserves the insertion location and function of the part.
- [far] `inserted front component` — Focuses on the insertion and front location without the head sphere.
- [near] `static component` — Preserves the static nature of the part.
- [far] `non-movable part` — Focuses on the non-movement property without the source noun.
- [far] `forward-facing structure` — Focuses on the directional property without the source noun.
- [far] `continuous surface` — Focuses on the surface continuity without the source noun.

**getty_aat**（5 条）
- [near] `facial landmark` — Preserves the concept of a facial landmark with a specific function.
- [far] `landmark feature` — Focuses on the functional role of a landmark without specifying the face.
- [near] `smooth surface finish` — Preserves the smooth surface property of the part.
- [far] `continuous surface` — Focuses on the surface continuity without the source noun.
- [far] `tapered form` — Focuses on the tapered shape without the source noun.

**asknature**（5 条）
- [near] `forward-pointing structure` — Preserves the directional property of the structure.
- [far] `directional protrusion` — Focuses on the directional aspect without the source noun.
- [far] `facial feature` — Focuses on the functional role of a facial feature.
- [far] `inserted structure` — Focuses on the insertion property without the source noun.
- [far] `non-movable structure` — Focuses on the static nature without the source noun.

## Santa Head（santa head）

部件：santa hat, beard, eyebrows

### 部件：santa hat（8.44s）

**失败**：Expecting value: line 51 column 20 (char 2092)

### 部件：beard（31.13s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：beard
- source_noun：santa head

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | bulky rounded mass | bulky rounded mass below the nose | which concrete cross-domain entities exhibit this same relational property? | 0.94 |
| attr_02 | selected_part_function | facial hair defining the face silhouette | facial hair defining the face silhouette | which concrete cross-domain entities exhibit this same relational property? | 0.94 |
| attr_03 | attachment_logic | covers the jaw and chin | covers the jaw and chin, wrapping around the mouth | which concrete cross-domain entities exhibit this same relational property? | 0.94 |
| attr_04 | orientation | spreads outward from the face | wraps around cheeks | which concrete cross-domain entities exhibit this same relational property? | 0.94 |
| attr_05 | articulation | soft and flowing | large fluffy mass covering the lower face | which concrete cross-domain entities exhibit this same relational property? | 0.94 |
| attr_06 | interface | attached to the face | wraps around cheeks | which concrete cross-domain entities exhibit this same relational property? | 0.94 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（6 条）
- [near] `bulky rounded mass` — Preserves the shape attribute by searching for entities with a similar bulky rounded mass.
- [far] `rounded mass` — Focuses on the rounded mass attribute without the source noun, searching for similar physical entities.
- [near] `covers the jaw` — Preserves the attachment logic attribute by searching for entities that cover the jaw.
- [far] `covering structure` — Focuses on the covering attribute without the source noun, searching for similar physical entities.
- [near] `attached to the face` — Preserves the interface attribute by searching for entities attached to the face.
- [far] `attached structure` — Focuses on the attachment attribute without the source noun, searching for similar physical entities.

**getty_aat**（6 条）
- [near] `facial hair` — Preserves the function attribute by searching for entities that define a face silhouette.
- [far] `defining silhouette` — Focuses on the silhouette attribute without the source noun, searching for similar aesthetic properties.
- [near] `soft flowing structure` — Preserves the articulation attribute by searching for entities with a soft and flowing texture.
- [far] `flowing texture` — Focuses on the flowing attribute without the source noun, searching for similar aesthetic properties.
- [near] `bulky mass` — Preserves the shape attribute by searching for entities with a similar bulky mass.
- [far] `rounded mass` — Focuses on the rounded mass attribute without the source noun, searching for similar aesthetic properties.

**asknature**（6 条）
- [near] `spreading structure` — Preserves the orientation attribute by searching for entities that spread outward.
- [far] `outward spreading` — Focuses on the spreading attribute without the source noun, searching for similar biological mechanisms.
- [near] `defining face silhouette` — Preserves the function attribute by searching for entities that define a face silhouette.
- [far] `defining silhouette` — Focuses on the silhouette attribute without the source noun, searching for similar biological strategies.
- [near] `covering jaw` — Preserves the attachment logic attribute by searching for entities that cover the jaw.
- [far] `covering structure` — Focuses on the covering attribute without the source noun, searching for similar biological mechanisms.

## Candle（candle）

部件：flame, wick, wax body

### 部件：flame（29.96s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：flame
- source_noun：candle

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | teardrop flame rising from the wick | small teardrop volume at the very top | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_02 | selected_part_function | emits light and heat | distinct from wax body | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_03 | attachment_logic | sits on top of the wick at the candle top | distinct from wax body | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_04 | orientation | vertical alignment | teardrop flame rising from the wick | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_05 | articulation | static form | distinct from wax body | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_06 | interface | top surface interface | sits on top of the wick at the candle top | which concrete cross-domain entities exhibit this same relational property? | 0.9 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（8 条）
- [near] `teardrop shape` — preserves the teardrop shape attribute of the flame
- [far] `teardrop form` — preserves the teardrop shape attribute across different domains
- [near] `light emitting object` — preserves the light-emitting function of the flame
- [far] `heat emitting object` — preserves the heat-emitting function across different domains
- [near] `vertical orientation` — preserves the vertical alignment attribute of the flame
- [far] `upright orientation` — preserves the vertical alignment attribute across different domains
- [near] `top surface interface` — preserves the top surface interface attribute of the flame
- [far] `surface attachment` — preserves the surface attachment attribute across different domains

**getty_aat**（4 条）
- [near] `top surface interface` — preserves the top surface interface attribute of the flame
- [far] `surface attachment` — preserves the surface attachment attribute across different domains
- [near] `top surface interface` — preserves the top surface interface attribute of the flame
- [far] `surface contact` — preserves the surface contact attribute across different domains

**asknature**（6 条）
- [near] `static structure` — preserves the static form attribute of the flame
- [far] `non-motile structure` — preserves the static form attribute across different domains
- [near] `teardrop shape` — preserves the teardrop shape attribute of the flame
- [far] `teardrop form` — preserves the teardrop shape attribute across different domains
- [near] `light emitting function` — preserves the light-emitting function of the flame
- [far] `heat emitting function` — preserves the heat-emitting function across different domains

### 部件：wick（112.98s）

**失败**：attribute query expansion returned no structured result

## Sled（sled）

部件：runner, seat, side rail

### 部件：runner（30.01s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：runner
- source_noun：sled

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | long curved blade | two long thin curved blades under the sled | which concrete cross-domain entities exhibit this same relational property? | 0.93 |
| attr_02 | selected_part_function | slides over snow and steers | upturned front tips | which concrete cross-domain entities exhibit this same relational property? | 0.93 |
| attr_03 | attachment_logic | curving up at the front | upturned front tips | which concrete cross-domain entities exhibit this same relational property? | 0.93 |
| attr_04 | orientation | horizontal alignment with the sled | two long thin curved blades under the sled | which concrete cross-domain entities exhibit this same relational property? | 0.93 |
| attr_05 | articulation | flexible front tips | upturned front tips | which concrete cross-domain entities exhibit this same relational property? | 0.93 |
| attr_06 | interface | direct contact with snow | two long thin curved blades under the sled | which concrete cross-domain entities exhibit this same relational property? | 0.93 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（8 条）
- [near] `curved blade` — Preserves the shape attribute by searching for entities with a similar curved blade structure.
- [far] `long curved blade` — Searches for entities with the same shape attribute across different domains.
- [near] `snow sliding mechanism` — Preserves the function attribute by searching for entities that slide over surfaces.
- [far] `steering mechanism` — Searches for entities with steering functionality across different domains.
- [near] `direct contact surface` — Preserves the interface attribute by searching for entities with direct contact surfaces.
- [far] `contact surface` — Searches for entities with contact surfaces across different domains.
- [near] `upturned front` — Preserves the attachment logic by searching for entities with upturned front structures.
- [far] `curved front` — Searches for entities with curved front structures across different domains.

**getty_aat**（6 条）
- [near] `upturned front` — Preserves the attachment logic by searching for entities with upturned front structures.
- [far] `curved front` — Searches for entities with curved front structures across different domains.
- [near] `horizontal alignment` — Preserves the orientation attribute by searching for entities with horizontal alignment.
- [far] `horizontal positioning` — Searches for entities with horizontal positioning across different domains.
- [near] `curved blade` — Preserves the shape attribute by searching for entities with a similar curved blade structure.
- [far] `long curved blade` — Searches for entities with the same shape attribute across different domains.

**asknature**（4 条）
- [near] `flexible tip` — Preserves the articulation attribute by searching for entities with flexible tips.
- [far] `flexible structure` — Searches for entities with flexible structures across different domains.
- [near] `snow sliding` — Preserves the function attribute by searching for entities that slide over surfaces.
- [far] `steering function` — Searches for entities with steering functionality across different domains.

### 部件：seat（54.35s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：seat
- source_noun：sled

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | flat horizontal platform | wide flat slab between the two sides | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_02 | selected_part_function | supports the rider | supports the rider | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_03 | attachment_logic | spans across the top of the sled frame | spans across the top of the sled frame | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_04 | orientation | horizontal | flat horizontal platform between the rails | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_05 | articulation | fixed | spans across the top of the sled frame | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_06 | interface | flat surface | wide flat slab between the two sides | which concrete cross-domain entities exhibit this same relational property? | 0.88 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（10 条）
- [near] `horizontal platform` — Preserves the shape and orientation of the platform.
- [far] `flat platform` — Retains the flatness and horizontal orientation of the platform.
- [near] `support structure` — Preserves the functional role of supporting a rider.
- [far] `support mechanism` — Retains the functional role of supporting a load or entity.
- [near] `spanning structure` — Preserves the spatial relationship of spanning across a frame.
- [far] `crossbar` — Retains the spatial relationship of spanning across a structure.
- [near] `horizontal surface` — Preserves the orientation of the surface.
- [far] `flat surface` — Retains the orientation and flatness of the surface.
- [near] `fixed attachment` — Preserves the fixed nature of the attachment.
- [far] `rigid connection` — Retains the fixed and rigid nature of the connection.

**getty_aat**（2 条）
- [near] `flat surface` — Preserves the flatness and surface quality.
- [far] `plane surface` — Retains the flatness and surface quality in a more abstract form.

**asknature**（6 条）
- [near] `horizontal support` — Preserves the horizontal and supportive nature of the platform.
- [far] `flat support` — Retains the flatness and supportive function in a biological context.
- [near] `support mechanism` — Preserves the functional role of supporting a rider.
- [far] `load support` — Retains the functional role of supporting a load or entity.
- [near] `spanning structure` — Preserves the spatial relationship of spanning across a frame.
- [far] `crossbar mechanism` — Retains the spatial relationship of spanning across a structure.

## Bell（bell）

部件：clapper, handle, bell body

### 部件：clapper（114.55s）

**失败**：attribute query expansion returned no structured result

### 部件：handle（117.35s）

**失败**：attribute query expansion returned no structured result

## Wreath（wreath）

部件：foliage ring, berries, bow

### 部件：foliage ring（36.07s）

**失败**：attribute query expansion incomplete: graphs={'wikidata': 4, 'getty_aat': 4, 'asknature': 3}, buckets={'near': 9, 'far': 2}, missing_graphs=[], missing_attributes=[]

### 部件：berries（35.57s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：berries
- source_noun：wreath

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | small spheres clustered on the ring | small round bumps on the ring | which concrete cross-domain entities exhibit this same relational property? | 0.85 |
| attr_02 | selected_part_function | color accent and texture contrast | small round bumps on the ring | which concrete cross-domain entities exhibit this same relational property? | 0.85 |
| attr_03 | attachment_logic | scattered on the foliage ring surface | small round bumps on the ring | which concrete cross-domain entities exhibit this same relational property? | 0.85 |
| attr_04 | articulation | non-attached, surface-based | small round bumps on the ring | which concrete cross-domain entities exhibit this same relational property? | 0.85 |
| attr_05 | orientation | randomly distributed on the surface | small round bumps on the ring | which concrete cross-domain entities exhibit this same relational property? | 0.85 |
| attr_06 | interface | surface contact with foliage ring | small round bumps on the ring | which concrete cross-domain entities exhibit this same relational property? | 0.85 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（6 条）
- [near] `small spherical cluster` — Preserves the shape and clustering attribute of the seed.
- [far] `clustered spherical formations` — Preserves the shape and clustering attribute across different domains.
- [near] `scattered surface elements` — Preserves the attachment and distribution attribute of the seed.
- [far] `surface-distributed features` — Preserves the attachment and distribution attribute across different domains.
- [near] `surface contact elements` — Preserves the interface and contact attribute of the seed.
- [far] `surface-contacting structures` — Preserves the interface and contact attribute across different domains.

**getty_aat**（6 条）
- [near] `texture contrast` — Preserves the function and visual attribute of the seed.
- [far] `visual contrast elements` — Preserves the function and visual attribute across different domains.
- [near] `surface-based elements` — Preserves the articulation and surface-based attribute of the seed.
- [far] `non-attached surface features` — Preserves the articulation and surface-based attribute across different domains.
- [near] `clustered spherical elements` — Preserves the shape and clustering attribute of the seed.
- [far] `spherical cluster formations` — Preserves the shape and clustering attribute across different domains.

**asknature**（6 条）
- [near] `randomly distributed structures` — Preserves the orientation and distribution attribute of the seed.
- [far] `randomly arranged biological features` — Preserves the orientation and distribution attribute across different domains.
- [near] `texture contrast mechanisms` — Preserves the function and visual attribute of the seed.
- [far] `visual contrast strategies` — Preserves the function and visual attribute across different domains.
- [near] `scattered surface features` — Preserves the attachment and distribution attribute of the seed.
- [far] `surface-distributed biological elements` — Preserves the attachment and distribution attribute across different domains.

## Gift Bag（gift bag）

部件：handle, bag body, folded top

### 部件：handle（122.59s）

**失败**：attribute query expansion returned no structured result

### 部件：bag body（120.67s）

**失败**：attribute query expansion returned no structured result

## Sock（sock）

部件：cuff, heel, toe

### 部件：cuff（81.87s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：cuff
- source_noun：sock

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | ribbed cylindrical band | ribbed band at the opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_02 | selected_part_function | holds the sock on the leg | ribbed band at the opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_03 | attachment_logic | attached to the top edge of the leg tube | ribbed band at the opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_04 | orientation | vertical cylindrical orientation | ribbed band at the opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_05 | articulation | non-articulated single band | ribbed band at the opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_06 | interface | smooth interface with leg tube | ribbed band at the opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（8 条）
- [near] `cylindrical band` — Preserves the cylindrical shape and ribbed feature of the selected part.
- [far] `ribbed band` — Focuses on the ribbed feature while omitting the source noun to search another domain.
- [near] `support band` — Preserves the functional role of holding in a physical context.
- [far] `support function` — Focuses on the functional aspect without the source noun to search another domain.
- [near] `smooth interface` — Preserves the smooth interface feature of the selected part.
- [far] `interface mechanism` — Focuses on the interface mechanism without the source noun to search another domain.
- [near] `edge attachment` — Preserves the attachment logic at the edge of a physical component.
- [far] `attachment interface` — Focuses on the attachment interface without the source noun to search another domain.

**getty_aat**（6 条）
- [near] `edge attachment` — Preserves the attachment logic at the edge of a physical component.
- [far] `attachment mechanism` — Focuses on the attachment mechanism without the source noun to search another domain.
- [near] `cylindrical form` — Preserves the cylindrical orientation of the selected part.
- [far] `vertical form` — Focuses on the vertical orientation without the source noun to search another domain.
- [near] `ribbed cylindrical form` — Preserves the cylindrical shape and ribbed feature of the selected part.
- [far] `ribbed form` — Focuses on the ribbed feature while omitting the source noun to search another domain.

**asknature**（4 条）
- [near] `single band structure` — Preserves the non-articulated, single band feature.
- [far] `non-articulated structure` — Focuses on the non-articulated structure without the source noun to search another domain.
- [near] `support function` — Preserves the functional role of holding in a physical context.
- [far] `support mechanism` — Focuses on the functional aspect without the source noun to search another domain.

### 部件：heel（115.15s）

**失败**：attribute query expansion returned no structured result

## Croissant（croissant）

部件：ridge, crescent tip, layered body

### 部件：ridge（30.46s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：ridge
- source_noun：croissant

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | raised crescent ridges | parallel curved raised bands | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_02 | selected_part_function | lamination visual and texture | parallel curved raised bands | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_03 | attachment_logic | concentric arcs on the upper surface | parallel curved raised bands | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_04 | orientation | horizontal alignment across the top | parallel curved raised bands | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_05 | articulation | continuous surface segment | parallel curved raised bands | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_06 | interface | textured surface interaction | parallel curved raised bands | which concrete cross-domain entities exhibit this same relational property? | 0.9 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（6 条）
- [near] `raised ridge` — Preserves the shape attribute by searching for similar physical entities with raised ridges.
- [far] `crescent shaped ridge` — Searches for entities with crescent-shaped ridges in different domains, maintaining the shape attribute.
- [near] `horizontal alignment` — Searches for entities with horizontal alignment in similar physical domains.
- [far] `horizontal surface alignment` — Searches for horizontal alignment in different physical domains, preserving the orientation attribute.
- [near] `lamination texture` — Focuses on the visual and tactile properties of lamination in similar domains.
- [near] `concentric arc structure` — Maintains the concentric arc geometry in similar physical domains.

**getty_aat**（6 条）
- [near] `lamination texture` — Focuses on aesthetic and material properties related to lamination and texture.
- [far] `textured lamination` — Searches for textured lamination in different domains, preserving the visual and tactile attribute.
- [near] `continuous surface` — Focuses on continuous surface properties in similar domains.
- [far] `continuous surface segment` — Searches for continuous surface segments in different domains, maintaining the surface continuity attribute.
- [near] `raised crescent shape` — Preserves the shape attribute by searching for similar aesthetic or material properties.
- [far] `arc pattern` — Searches for arc patterns in different domains, preserving the geometric attribute.

**asknature**（6 条）
- [near] `concentric arc structure` — Maintains the concentric arc geometry in biological or mechanical contexts.
- [far] `arc pattern in organisms` — Searches for arc patterns in different biological systems, preserving the geometric attribute.
- [near] `textured surface interaction` — Searches for entities with textured surface interactions in similar biological contexts.
- [far] `surface texture interaction` — Searches for surface texture interactions in different biological systems, preserving the tactile attribute.
- [far] `crescent shaped ridge` — Searches for crescent-shaped ridges in different biological or mechanical systems.
- [far] `textured lamination` — Searches for textured lamination in different biological or mechanical systems.

### 部件：crescent tip（30.87s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：crescent tip
- source_noun：croissant

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | tapered pointed ends curving inward | two tapered inward-curving tips | which concrete cross-domain entities exhibit this same relational property? | 0.87 |
| attr_02 | selected_part_function | defines the crescent silhouette | two tapered inward-curving tips | which concrete cross-domain entities exhibit this same relational property? | 0.87 |
| attr_03 | attachment_logic | two ends of the crescent body | two tapered inward-curving tips | which concrete cross-domain entities exhibit this same relational property? | 0.87 |
| attr_04 | orientation | pointed ends facing outward | two tapered inward-curving tips | which concrete cross-domain entities exhibit this same relational property? | 0.87 |
| attr_05 | articulation | smooth transition between tips and body | two tapered inward-curving tips | which concrete cross-domain entities exhibit this same relational property? | 0.87 |
| attr_06 | interface | sharp edges at the tips | two tapered inward-curving tips | which concrete cross-domain entities exhibit this same relational property? | 0.87 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（6 条）
- [near] `tapered pointed end` — Preserves the tapered inward-curving shape of the crescent tip.
- [far] `inward-curving tapered tip` — Searches for entities with inward-curving tapered ends in different domains.
- [near] `two ends of a body` — Preserves the two-ended structure of the crescent body.
- [far] `two-ended structure` — Searches for entities with two-ended structures in different domains.
- [near] `sharp pointed edges` — Preserves the sharp edges at the tips of the crescent.
- [far] `sharp edge structure` — Searches for entities with sharp edges in different domains.

**getty_aat**（8 条）
- [near] `crescent shape` — Preserves the defining shape of the crescent silhouette.
- [far] `silhouette defining form` — Searches for entities that define a silhouette in different domains.
- [near] `pointed outward ends` — Preserves the outward-facing pointed ends of the crescent.
- [far] `outward-facing points` — Searches for entities with outward-facing points in different domains.
- [near] `tapered inward-curving form` — Preserves the tapered inward-curving shape of the crescent tip.
- [far] `inward-curving tapered form` — Searches for entities with inward-curving tapered forms in different domains.
- [near] `two-ended body structure` — Preserves the two-ended structure of the crescent body.
- [far] `two-ended form` — Searches for entities with two-ended forms in different domains.

**asknature**（4 条）
- [near] `smooth transition between parts` — Preserves the smooth articulation between tips and body.
- [far] `gradual part transition` — Searches for entities with gradual transitions between parts in different domains.
- [near] `silhouette defining structure` — Preserves the defining shape of the crescent silhouette.
- [far] `shape-defining form` — Searches for entities that define a silhouette in different domains.

## Pretzel（pretzel）

部件：twist knot, loop segment, rope body

### 部件：twist knot（30.25s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：twist knot
- source_noun：pretzel

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | overlapping twist crossover | central overlapping crossover | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_02 | selected_part_function | distinctive braid structure | central overlapping crossover | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_03 | attachment_logic | center of the pretzel where strands cross | central overlapping crossover | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_04 | articulation | twisted strands forming a knot | central overlapping crossover | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_05 | orientation | symmetrical twist around central axis | central overlapping crossover | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_06 | interface | interlocking strands at the knot | central overlapping crossover | which concrete cross-domain entities exhibit this same relational property? | 0.9 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（6 条）
- [near] `twist crossover` — Preserves the overlapping twist crossover attribute by searching for similar physical entities.
- [far] `overlapping twist` — Searches for entities with overlapping twist properties in a different domain.
- [near] `crossing strands` — Preserves the crossing strands attribute by searching for similar physical entities.
- [far] `strands crossing` — Searches for entities with crossing strands in a different domain.
- [near] `interlocking strands` — Preserves the interlocking strands attribute by searching for similar physical entities.
- [far] `interlocking mechanism` — Searches for entities with interlocking mechanisms in a different domain.

**getty_aat**（6 条）
- [near] `braid structure` — Preserves the braid structure attribute by searching for similar aesthetic or craft terms.
- [far] `interwoven structure` — Searches for entities with interwoven structures in a different domain.
- [near] `symmetrical twist` — Preserves the symmetrical twist attribute by searching for similar aesthetic or craft terms.
- [far] `central symmetry` — Searches for entities with central symmetry in a different domain.
- [near] `twist crossover` — Preserves the overlapping twist crossover attribute by searching for similar aesthetic or craft terms.
- [far] `overlapping twist` — Searches for entities with overlapping twist properties in a different domain.

**asknature**（6 条）
- [near] `twisted strands` — Preserves the twisted strands attribute by searching for similar biological mechanisms.
- [far] `knot formation` — Searches for entities with knot formation in a different domain.
- [near] `braid structure` — Preserves the braid structure attribute by searching for similar biological mechanisms.
- [far] `interwoven structure` — Searches for entities with interwoven structures in a different domain.
- [near] `crossing strands` — Preserves the crossing strands attribute by searching for similar biological mechanisms.
- [far] `strands crossing` — Searches for entities with crossing strands in a different domain.

### 部件：loop segment（110.25s）

**失败**：attribute query expansion returned no structured result
