# Planner 稳定性测试报告

- 模型数：7
- 部件级测试数：9，成功：7，失败：2
- 总耗时：802.38s
- planner：http://127.0.0.1:18085/v1

## Santa Head（santa head）

部件：santa hat

### 部件：santa hat（36.7s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：santa hat
- source_noun：santa head

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | soft conical cap with folded brim and pom-pom | conical mass above the head, pom ball at the tip | which concrete cross-domain entities exhibit this same relational property? | 0.93 |
| attr_02 | selected_part_function | head covering and festive marker | conical mass above the head, pom ball at the tip | which concrete cross-domain entities exhibit this same relational property? | 0.93 |
| attr_03 | attachment_logic | sits on top of the head and forehead | conical mass above the head, pom ball at the tip | which concrete cross-domain entities exhibit this same relational property? | 0.93 |
| attr_04 | articulation | non-articulated fixed structure | conical mass above the head, pom ball at the tip | which concrete cross-domain entities exhibit this same relational property? | 0.93 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（8 条）
- [near] `conical cap` — Preserves the conical shape and cap structure of the seed attribute.
- [far] `conical shape` — Focuses on the conical geometry, which is a core attribute of the seed.
- [near] `head covering` — Preserves the function of covering the head.
- [far] `festive marker` — Focuses on the festive function as a marker.
- [near] `head attachment` — Preserves the attachment to the head.
- [far] `forehead attachment` — Focuses on the forehead as a surface for attachment.
- [near] `fixed structure` — Preserves the fixed structure as a key attribute.
- [far] `non-articulated form` — Focuses on the non-articulated form as a structural feature.

**getty_aat**（8 条）
- [near] `conical form` — Maintains the conical form as a key aesthetic component.
- [far] `folded brim` — Focuses on the folded brim as a form element.
- [near] `festive ornament` — Maintains the festive marker as an ornament.
- [far] `head ornament` — Focuses on the head ornament as a functional and decorative element.
- [near] `head placement` — Maintains the placement on the head.
- [far] `surface attachment` — Focuses on the surface-based attachment mechanism.
- [near] `fixed form` — Maintains the fixed form as a key aesthetic component.
- [far] `non-articulated structure` — Focuses on the non-articulated structure as a craft element.

**asknature**（8 条）
- [near] `conical structure` — Preserves the conical shape as a structural feature.
- [far] `pom-pom structure` — Focuses on the pom-pom as a biological or mechanical structure.
- [near] `festive display` — Preserves the festive function as a display.
- [far] `signal marker` — Focuses on the marker function as a signaling mechanism.
- [near] `head placement` — Preserves the placement on the head.
- [far] `surface contact` — Focuses on the contact mechanism as a biological strategy.
- [near] `fixed mechanism` — Preserves the fixed structure as a mechanical feature.
- [far] `non-articulated system` — Focuses on the non-articulated system as a biological strategy.

## Candle（candle）

部件：wick

### 部件：wick（127.07s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：wick
- source_noun：candle

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | thin vertical stalk | thin vertical column between wax and flame | which concrete cross-domain entities exhibit this same relational property? | 0.78 |
| attr_02 | selected_part_function | conducts melted wax to the flame | thin vertical column between wax and flame | which concrete cross-domain entities exhibit this same relational property? | 0.78 |
| attr_03 | attachment_logic | embedded in the top center of the wax body | embedded in the top center of the wax body | which concrete cross-domain entities exhibit this same relational property? | 0.78 |
| attr_04 | orientation | vertical alignment | thin vertical column between wax and flame | which concrete cross-domain entities exhibit this same relational property? | 0.78 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（8 条）
- [near] `thin vertical column` — Preserves the shape attribute of thin vertical stalk by searching for similar physical entities.
- [far] `thin vertical rod` — Searches for entities with a similar geometric property of thin vertical structure across different domains.
- [near] `conductive column` — Preserves the function of conducting melted material by searching for similar physical entities.
- [far] `heat transfer rod` — Searches for entities with similar conductive properties across different domains.
- [near] `central attachment` — Preserves the attachment logic of central embedding by searching for similar physical entities.
- [far] `central fitting` — Searches for entities with similar central attachment properties across different domains.
- [near] `vertical structure` — Preserves the orientation of vertical alignment by searching for similar physical entities.
- [far] `upright form` — Searches for entities with similar vertical orientation properties across different domains.

**getty_aat**（8 条）
- [near] `vertical form` — Focuses on aesthetic/form vocabulary related to vertical shapes.
- [far] `slender column` — Searches for similar vertical forms in different domains using form vocabulary.
- [near] `conductive form` — Focuses on aesthetic/form vocabulary related to conductive structures.
- [far] `heat transfer mechanism` — Searches for similar conductive mechanisms in different domains using form vocabulary.
- [near] `central form` — Focuses on aesthetic/form vocabulary related to central attachment.
- [far] `central fitting mechanism` — Searches for similar central attachment mechanisms in different domains using form vocabulary.
- [near] `vertical form` — Focuses on aesthetic/form vocabulary related to vertical orientation.
- [far] `upright structure` — Searches for similar vertical orientation structures in different domains using form vocabulary.

**asknature**（8 条）
- [near] `vertical support structure` — Focuses on biological mechanisms with vertical support properties.
- [far] `slender vertical stem` — Searches for biological structures with slender vertical forms across different domains.
- [near] `heat transfer conduit` — Focuses on biological mechanisms with heat transfer properties.
- [far] `fluid transport structure` — Searches for biological structures with fluid transport properties across different domains.
- [near] `central support structure` — Focuses on biological mechanisms with central support properties.
- [far] `central attachment strategy` — Searches for biological structures with central attachment properties across different domains.
- [near] `vertical support` — Focuses on biological mechanisms with vertical orientation properties.
- [far] `upright mechanism` — Searches for biological structures with vertical orientation properties across different domains.

## Bell（bell）

部件：clapper, handle

### 部件：clapper（180.42s）

**失败**：query items did not satisfy the schema or coverage requirements

### 部件：handle（39.61s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：handle
- source_noun：bell

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | small loop or knob | loop/knob above the domed body | which concrete cross-domain entities exhibit this same relational property? | 0.82 |
| attr_02 | selected_part_function | holding and hanging point | loop/knob above the domed body | which concrete cross-domain entities exhibit this same relational property? | 0.82 |
| attr_03 | attachment_logic | attached to the crown of the bell body | loop/knob above the domed body | which concrete cross-domain entities exhibit this same relational property? | 0.82 |
| attr_04 | orientation | vertically aligned | loop/knob above the domed body | which concrete cross-domain entities exhibit this same relational property? | 0.82 |
| attr_05 | articulation | fixed attachment | loop/knob above the domed body | which concrete cross-domain entities exhibit this same relational property? | 0.82 |
| attr_06 | interface | smooth surface | loop/knob above the domed body | which concrete cross-domain entities exhibit this same relational property? | 0.82 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（12 条）
- [near] `loop` — searches for physical entities with a loop shape, preserving the selected part shape attribute.
- [near] `knob` — searches for physical entities with a knob shape, preserving the selected part shape attribute.
- [far] `handle` — searches for physical entities with a handle, which may exhibit a similar shape attribute in a different domain.
- [far] `attachment` — searches for physical entities with an attachment feature, which may exhibit a similar shape attribute in a different domain.
- [near] `crown attachment` — searches for physical entities with a crown attachment, preserving the attachment logic attribute.
- [near] `bell attachment` — searches for physical entities with a bell attachment, preserving the attachment logic attribute.
- [far] `crown` — searches for physical entities with a crown feature, which may exhibit a similar attachment logic in a different domain.
- [far] `attachment` — searches for physical entities with an attachment feature, which may exhibit a similar attachment logic in a different domain.
- [near] `smooth surface` — searches for physical entities with a smooth surface, preserving the interface attribute.
- [near] `polished surface` — searches for physical entities with a polished surface, preserving the interface attribute.
- [far] `surface` — searches for physical entities with a surface feature, which may exhibit a similar interface in a different domain.
- [far] `texture` — searches for physical entities with a texture feature, which may exhibit a similar interface in a different domain.

**getty_aat**（8 条）
- [near] `hanging device` — searches for artifact components with a holding and hanging function, preserving the selected part function attribute.
- [near] `support mechanism` — searches for artifact components with a holding and hanging function, preserving the selected part function attribute.
- [far] `hanger` — searches for physical entities with a hanger function, which may exhibit a similar function attribute in a different domain.
- [far] `attachment point` — searches for physical entities with an attachment point, which may exhibit a similar function attribute in a different domain.
- [near] `fixed attachment` — searches for artifact components with a fixed attachment, preserving the articulation attribute.
- [near] `permanent attachment` — searches for artifact components with a permanent attachment, preserving the articulation attribute.
- [far] `attachment` — searches for physical entities with an attachment feature, which may exhibit a similar articulation in a different domain.
- [far] `fixed mechanism` — searches for physical entities with a fixed mechanism, which may exhibit a similar articulation in a different domain.

**asknature**（4 条）
- [near] `vertical alignment` — searches for biological mechanisms with vertical alignment, preserving the orientation attribute.
- [near] `symmetrical structure` — searches for biological mechanisms with symmetrical structure, preserving the orientation attribute.
- [far] `vertical orientation` — searches for biological mechanisms with vertical orientation, which may exhibit a similar orientation in a different domain.
- [far] `alignment strategy` — searches for biological mechanisms with alignment strategy, which may exhibit a similar orientation in a different domain.

## Wreath（wreath）

部件：foliage ring

### 部件：foliage ring（129.07s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：foliage ring
- source_noun：wreath

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | layered leaf texture around the loop | layered leaf texture around the loop | which concrete cross-domain entities exhibit this same relational property? | 0.95 |
| attr_02 | selected_part_function | structural ring and decorative body | dominant circular band, layered leaf texture around the loop | which concrete cross-domain entities exhibit this same relational property? | 0.95 |
| attr_03 | attachment_logic | continuous circular band forming the wreath | continuous circular band forming the wreath | which concrete cross-domain entities exhibit this same relational property? | 0.95 |
| attr_04 | orientation | circular loop aligned with the wreath's perimeter | dominant circular band | which concrete cross-domain entities exhibit this same relational property? | 0.95 |
| attr_05 | articulation | continuous and unbroken leaf layering | layered leaf texture around the loop | which concrete cross-domain entities exhibit this same relational property? | 0.95 |
| attr_06 | interface | smooth and continuous surface with no gaps | continuous circular band forming the wreath | which concrete cross-domain entities exhibit this same relational property? | 0.95 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（8 条）
- [near] `layered leaf texture` — Preserves the layered leaf texture attribute within the same physical domain.
- [far] `circular leaf pattern` — Preserves the layered leaf texture attribute across a different physical domain.
- [near] `circular loop` — Preserves the circular loop attribute within the same physical domain.
- [far] `perimeter ring` — Preserves the circular loop attribute across a different physical domain.
- [near] `decorative ring` — Preserves the structural ring attribute within the same physical domain.
- [far] `circular band` — Preserves the continuous circular band attribute across a different physical domain.
- [near] `continuous leaf layering` — Preserves the continuous leaf layering attribute within the same physical domain.
- [near] `continuous surface` — Preserves the continuous surface attribute within the same physical domain.

**getty_aat**（8 条）
- [near] `circular band` — Preserves the structural ring attribute within the same aesthetic domain.
- [far] `ornamental ring` — Preserves the structural ring attribute across a different aesthetic domain.
- [near] `continuous leaf layering` — Preserves the continuous leaf layering attribute within the same aesthetic domain.
- [far] `unbroken leaf pattern` — Preserves the continuous leaf layering attribute across a different aesthetic domain.
- [near] `layered leaf pattern` — Preserves the layered leaf texture attribute within the same aesthetic domain.
- [near] `continuous circular band` — Preserves the continuous circular band attribute within the same aesthetic domain.
- [near] `looped structure` — Preserves the circular loop attribute within the same aesthetic domain.
- [far] `gapless surface` — Preserves the continuous surface attribute across a different aesthetic domain.

**asknature**（7 条）
- [near] `continuous circular structure` — Preserves the continuous circular band attribute within the same biological domain.
- [far] `circular growth pattern` — Preserves the continuous circular band attribute across a different biological domain.
- [near] `continuous surface` — Preserves the continuous surface attribute within the same biological domain.
- [far] `gapless surface` — Preserves the continuous surface attribute across a different biological domain.
- [far] `layered leaf structure` — Preserves the layered leaf texture attribute across a different biological domain.
- [far] `structural ring` — Preserves the structural ring attribute across a different biological domain.
- [far] `looped growth` — Preserves the circular loop attribute across a different biological domain.

## Gift Bag（gift bag）

部件：handle, bag body

### 部件：handle（31.29s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：handle
- source_noun：gift bag

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | two ribbon loops rising from the top edges | two loops above the bag opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_02 | selected_part_function | carrying grip | attached to the folded top of the bag | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_03 | attachment_logic | attached to the folded top of the bag | attached to the folded top of the bag | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_04 | orientation | horizontal orientation | two loops above the bag opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_05 | articulation | non-articulated | two loops above the bag opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_06 | interface | loop interface | two loops above the bag opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（5 条）
- [near] `loop` — searches for entities with a loop shape, preserving the selected part shape attribute.
- [near] `attachment` — searches for entities with an attachment mechanism, preserving the attachment logic attribute.
- [far] `fastening` — searches for entities with a fastening mechanism across different domains, preserving the attachment logic attribute.
- [near] `loop` — searches for entities with a loop interface, preserving the interface attribute.
- [far] `loop mechanism` — searches for entities with a loop mechanism across different domains, preserving the interface attribute.

**getty_aat**（5 条）
- [near] `carrying handle` — searches for artifact components with a carrying function, preserving the selected part function attribute.
- [far] `grip` — searches for entities with a gripping function across different domains, preserving the selected part function attribute.
- [near] `horizontal` — searches for entities with a horizontal orientation, preserving the orientation attribute.
- [far] `horizontal arrangement` — searches for entities with a horizontal arrangement across different domains, preserving the orientation attribute.
- [near] `loop` — searches for artifact components with a loop shape, preserving the selected part shape attribute.

**asknature**（6 条）
- [near] `non-articulated structure` — searches for biological structures without articulation, preserving the articulation attribute.
- [far] `rigid structure` — searches for rigid biological structures across different domains, preserving the articulation attribute.
- [near] `grip` — searches for biological mechanisms with a gripping function, preserving the selected part function attribute.
- [far] `claw` — searches for entities with a claw-like gripping function across different domains, preserving the selected part function attribute.
- [near] `attachment` — searches for biological attachment mechanisms, preserving the attachment logic attribute.
- [far] `fastening` — searches for entities with a fastening mechanism across different domains, preserving the attachment logic attribute.

### 部件：bag body（29.9s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：bag body
- source_noun：gift bag

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | tall box-like body with tapered bottom | dominant vertical container volume | which concrete cross-domain entities exhibit this same relational property? | 0.95 |
| attr_02 | selected_part_function | holds contents | dominant vertical container volume | which concrete cross-domain entities exhibit this same relational property? | 0.95 |
| attr_03 | attachment_logic | the main volume between top fold and base | dominant vertical container volume | which concrete cross-domain entities exhibit this same relational property? | 0.95 |
| attr_04 | orientation | vertical | dominant vertical container volume | which concrete cross-domain entities exhibit this same relational property? | 0.95 |
| attr_05 | articulation | non-articulated | dominant vertical container volume | which concrete cross-domain entities exhibit this same relational property? | 0.95 |
| attr_06 | interface | smooth surface | dominant vertical container volume | which concrete cross-domain entities exhibit this same relational property? | 0.95 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（8 条）
- [near] `container with tapered base` — Preserves the shape attribute by focusing on a container with a tapered base.
- [far] `tapered container` — Focuses on the tapered shape attribute across different domains.
- [near] `container` — Preserves the function attribute by focusing on the primary function of holding contents.
- [far] `storage vessel` — Focuses on the function of holding contents across different domains.
- [near] `tapered box` — Preserves the shape attribute by focusing on a tapered box.
- [far] `tapered form` — Focuses on the tapered form attribute across different domains.
- [near] `main body volume` — Preserves the attachment logic by focusing on the main body volume.
- [far] `central volume` — Focuses on the central volume attribute across different domains.

**getty_aat**（6 条）
- [near] `main body` — Preserves the attachment logic by focusing on the main body structure.
- [far] `central volume` — Focuses on the central volume attribute across different domains.
- [near] `vertical form` — Preserves the orientation attribute by focusing on vertical form.
- [far] `upright structure` — Focuses on the vertical orientation attribute across different domains.
- [near] `storage function` — Preserves the function attribute by focusing on the storage function.
- [far] `container function` — Focuses on the container function attribute across different domains.

**asknature**（4 条）
- [near] `non-movable joint` — Preserves the articulation attribute by focusing on non-movable joints.
- [far] `rigid structure` — Focuses on the non-articulated structure attribute across different domains.
- [near] `smooth surface` — Preserves the interface attribute by focusing on smooth surface.
- [far] `continuous surface` — Focuses on the smooth surface attribute across different domains.

## Sock（sock）

部件：heel

### 部件：heel（37.68s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：heel
- source_noun：sock

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | rounded bend | sharp rear bend in the foot tube | which concrete cross-domain entities exhibit this same relational property? | 0.84 |
| attr_02 | selected_part_function | wraps the heel | sharp rear bend in the foot tube | which concrete cross-domain entities exhibit this same relational property? | 0.84 |
| attr_03 | attachment_logic | rear corner of the foot tube | sharp rear bend in the foot tube | which concrete cross-domain entities exhibit this same relational property? | 0.84 |
| attr_04 | orientation | vertical alignment | sharp rear bend in the foot tube | which concrete cross-domain entities exhibit this same relational property? | 0.84 |
| attr_05 | articulation | flexible bend | sharp rear bend in the foot tube | which concrete cross-domain entities exhibit this same relational property? | 0.84 |
| attr_06 | interface | seamless connection | sharp rear bend in the foot tube | which concrete cross-domain entities exhibit this same relational property? | 0.84 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（12 条）
- [near] `foot tube` — Preserves the shape attribute of the foot tube with a rounded bend.
- [far] `pipe bend` — Preserves the shape attribute of a rounded bend in a different physical domain.
- [near] `footwear component` — Preserves the function attribute of wrapping the heel in a footwear context.
- [far] `support structure` — Preserves the function attribute of wrapping in a different physical domain.
- [near] `footwear attachment` — Preserves the attachment logic attribute of the rear corner in a footwear context.
- [far] `structural corner` — Preserves the attachment logic attribute of a corner in a different physical domain.
- [near] `footwear alignment` — Preserves the orientation attribute of vertical alignment in a footwear context.
- [far] `vertical structure` — Preserves the orientation attribute of vertical alignment in a different physical domain.
- [near] `flexible pipe` — Preserves the articulation attribute of a flexible bend in a similar physical domain.
- [far] `flexible joint` — Preserves the articulation attribute of a flexible bend in a different physical domain.
- [near] `footwear seam` — Preserves the interface attribute of a seamless connection in a footwear context.
- [far] `seamless joint` — Preserves the interface attribute of a seamless connection in a different physical domain.

**getty_aat**（8 条）
- [near] `pipe bend` — Preserves the shape attribute of a rounded bend in an artifact context.
- [far] `curved joint` — Preserves the shape attribute of a rounded bend in a different artifact domain.
- [near] `footwear wrap` — Preserves the function attribute of wrapping the heel in an artifact context.
- [far] `support wrap` — Preserves the function attribute of wrapping in a different artifact domain.
- [near] `footwear corner` — Preserves the attachment logic attribute of a rear corner in an artifact context.
- [far] `structural corner` — Preserves the attachment logic attribute of a corner in a different artifact domain.
- [near] `vertical alignment` — Preserves the orientation attribute of vertical alignment in an artifact context.
- [far] `vertical structure` — Preserves the orientation attribute of vertical alignment in a different artifact domain.

**asknature**（4 条）
- [near] `flexible joint` — Preserves the articulation attribute of a flexible bend in a biological context.
- [far] `flexible connection` — Preserves the articulation attribute of a flexible bend in a different biological domain.
- [near] `seamless joint` — Preserves the interface attribute of a seamless connection in a biological context.
- [far] `seamless link` — Preserves the interface attribute of a seamless connection in a different biological domain.

## Pretzel（pretzel）

部件：loop segment

### 部件：loop segment（190.65s）

**失败**：query items did not satisfy the schema or coverage requirements
