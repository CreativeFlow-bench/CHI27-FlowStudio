# Planner 稳定性测试报告

- 模型数：10
- 部件级测试数：20，成功：20，失败：0
- 总耗时：1480.01s
- planner：http://127.0.0.1:18085/v1

## Snowman（snowman）

部件：top hat, carrot nose, scarf

### 部件：top hat（66.16s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：top hat
- source_noun：snowman

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | tall cylindrical brimmed hat | uppermost segment with cylindrical crown | which concrete cross-domain entities exhibit this same relational property? | 0.92 |
| attr_02 | selected_part_function | head covering and festive silhouette | brim wider than head | which concrete cross-domain entities exhibit this same relational property? | 0.92 |
| attr_03 | attachment_logic | rests on the head sphere | attachment to the head sphere | which concrete cross-domain entities exhibit this same relational property? | 0.92 |
| attr_04 | orientation | vertical alignment | uppermost segment with cylindrical crown | which concrete cross-domain entities exhibit this same relational property? | 0.92 |
| attr_05 | articulation | non-articulated fixed structure | brim wider than head | which concrete cross-domain entities exhibit this same relational property? | 0.92 |
| attr_06 | interface | flat surface interface | brim wider than head | which concrete cross-domain entities exhibit this same relational property? | 0.92 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（18 条）
- `cylinder` — the cylinder exhibits a tall cylindrical shape similar to the brimmed hat
- `column` — the column exhibits a tall cylindrical form akin to the brimmed hat
- `pillar` — the pillar exhibits a tall cylindrical structure similar to the brimmed hat
- `feather headdress` — feather headdress provides head coverage and has a festive, ornate silhouette
- `coral tree` — coral tree has a wide, branching structure that covers the head and forms a festive silhouette
- `woven basket` — woven basket can be shaped to cover the head and create a festive, structured silhouette
- `feather` — how the donor exhibits rests on the head sphere
- `antler` — how the donor exhibits rests on the head sphere
- `horn` — how the donor exhibits rests on the head sphere
- `column` — how the donor exhibits vertical alignment
- `spire` — how the donor exhibits vertical alignment
- `tower` — how the donor exhibits vertical alignment
- `stone pillar` — stone pillar exhibits non-articulated fixed structure through its solid, unbroken form
- `wooden beam` — wooden beam exhibits non-articulated fixed structure through its continuous, unbroken form
- `metal frame` — metal frame exhibits non-articulated fixed structure through its rigid, unbroken form
- `flat stone` — flat stone has a flat surface interface similar to the top hat's brim
- `sheet metal` — sheet metal provides a flat surface interface akin to the top hat's brim
- `tile floor` — tile floor exhibits a flat surface interface comparable to the top hat's brim

**getty_aat**（18 条）
- `cylindrical shell` — the cylindrical shell exhibits a tall cylindrical form similar to the brimmed hat
- `columnar structure` — the columnar structure exhibits a tall cylindrical form similar to the brimmed hat
- `tall spire` — the tall spire exhibits a tall cylindrical form similar to the brimmed hat
- `feathered headdress` — feathered headdress provides head coverage and adds a festive silhouette through its ornate structure
- `plumed cap` — plumed cap offers head coverage and creates a festive silhouette with its decorative plumes
- `corona` — corona serves as a head covering and forms a festive silhouette through its circular, ornamental shape
- `cap` — a cap rests on the head sphere by fitting over it
- `crown` — a crown rests on the head sphere by encircling it
- `helmet` — a helmet rests on the head sphere by enclosing it
- `column` — column maintains vertical alignment through its upright structure
- `spire` — spire exhibits vertical alignment through its elongated, upward form
- `pillar` — pillar demonstrates vertical alignment through its straight, upright orientation
- `clay tile` — clay tile forms a non-articulated fixed structure with a wide, unbroken surface
- `stone slab` — stone slab forms a non-articulated fixed structure with a wide, unbroken surface
- `wood panel` — wood panel forms a non-articulated fixed structure with a wide, unbroken surface
- `flat plane` — a flat plane exhibits a flat surface interface by having a uniform, level surface.
- `mirror surface` — a mirror surface exhibits a flat surface interface by reflecting light uniformly across a level plane.
- `glass pane` — a glass pane exhibits a flat surface interface by maintaining a smooth, level surface without irregularities.

**asknature**（18 条）
- `spider web silks` — spider web silks exhibit a tall cylindrical structure with a brimmed-like pattern
- `elephant trunk` — elephant trunk has a tall cylindrical shape with a brimmed-like expansion at the end
- `mushroom cap` — mushroom cap exhibits a tall cylindrical form with a brimmed-like edge
- `butterfly wing pattern` — butterfly wings have a wide, decorative shape that can cover and accentuate the body, similar to a festive silhouette
- `peacock feather` — peacock feathers have a wide, ornate shape that can cover and accentuate the body, similar to a festive silhouette
- `mantis shrimp claw` — mantis shrimp claws have a wide, striking shape that can cover and accentuate the body, similar to a festive silhouette
- `beaver tail` — the beaver tail rests on the body, similar to how a top hat rests on the head sphere
- `elephant trunk` — the elephant trunk rests on the head, similar to how a top hat rests on the head sphere
- `chimpanzee hand` — the chimpanzee hand rests on the head, similar to how a top hat rests on the head sphere
- `spider web` — spider web exhibits vertical alignment through its radial symmetry and central hub structure
- `bee hive` — bee hive exhibits vertical alignment through its hexagonal cell arrangement and vertical orientation
- `fern frond` — fern frond exhibits vertical alignment through its central vein and upward growth pattern
- `beaver dam` — beaver dam is a non-articulated fixed structure that remains rigid and immobile in its environment
- `termite mound` — termite mound is a non-articulated fixed structure that maintains its shape without moving parts
- `coral reef` — coral reef is a non-articulated fixed structure that remains rigid and immobile in its environment
- `butterfly wing` — butterfly wings have a flat, smooth surface that interacts with air efficiently
- `lotus leaf` — lotus leaves have a flat, hydrophobic surface that repels water
- `shark skin` — shark skin has a flat, textured surface that reduces drag in water

### 部件：carrot nose（70.41s）

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
| attr_06 | interface | smooth surface contact | no visible seams or joints | which concrete cross-domain entities exhibit this same relational property? | 0.9 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（18 条）
- `elephant trunk` — the elephant trunk is a tapered, forward-pointing structure that resembles a cone
- `narwhal tusk` — the narwhal tusk is a long, tapered, forward-pointing cone-like structure
- `dolphin beak` — the dolphin beak is a tapered, forward-pointing structure that resembles a cone
- `human nose` — the human nose serves as a facial landmark with a distinct shape and function similar to the carrot nose
- `elephant trunk` — the elephant trunk is a facial structure that acts as a landmark with a unique, contrasting shape
- `rhinoceros horn` — the rhinoceros horn is a facial feature that functions as a landmark with a distinct, protruding shape
- `beak` — the beak is inserted in the lower front of the head sphere
- `snout` — the snout is inserted in the lower front of the head sphere
- `nose` — the nose is inserted in the lower front of the head sphere
- `spider web` — spider web extends forward from the central point
- `antler` — antler projects forward from the skull
- `arrowhead` — arrowhead points forward from the shaft
- `Stalagmite` — stalagmites are static formations that do not move or flex
- `Rock Face` — rock faces are static and do not exhibit movement or flexibility
- `Crystal Lattice` — crystal lattices are static structures with no movement or flexibility
- `glass surface` — glass surface exhibits smooth surface contact through its homogeneous molecular structure
- `ice surface` — ice surface exhibits smooth surface contact through its crystalline molecular arrangement
- `oily skin` — oily skin exhibits smooth surface contact through its lipid layer reducing friction

**getty_aat**（18 条）
- `beak shape` — the beak shape exhibits a tapered, forward-pointing cone structure
- `spiral shell` — the spiral shell exhibits a tapered, forward-pointing cone structure
- `arrowhead form` — the arrowhead form exhibits a tapered, forward-pointing cone structure
- `nose bridge` — the nose bridge serves as a central structural feature, analogous to the nose landmark of the face
- `chin prominence` — the chin prominence functions as a distinct facial landmark, similar to the nose landmark of the face
- `forehead center` — the forehead center acts as a key facial landmark, comparable to the nose landmark of the face
- `nose ornament` — a nose ornament is inserted in the lower front of the head sphere as a decorative component
- `beak ornament` — a beak ornament is inserted in the lower front of the head sphere as a decorative feature
- `frontal crest` — a frontal crest is inserted in the lower front of the head sphere as a structural or decorative element
- `spiral shell` — spiral shell exhibits forward-pointing through its coiled, directed growth pattern
- `arrowhead` — arrowhead exhibits forward-pointing through its sharp, directed tip
- `beak shape` — beak shape exhibits forward-pointing through its elongated, directed form
- `stone pillar` — stone pillar lacks movement or flexibility
- `wooden beam` — wooden beam lacks movement or flexibility
- `metal bracket` — metal bracket lacks movement or flexibility
- `polished stone` — polished stone exhibits smooth surface contact through fine grinding and polishing
- `glass surface` — glass surface exhibits smooth surface contact through inherent material properties and manufacturing
- `wax finish` — wax finish exhibits smooth surface contact through application of a thin, even layer

**asknature**（18 条）
- `beaver tail` — the beaver tail is a tapered, cone-like structure that protrudes forward, similar to the carrot nose
- `elephant trunk` — the elephant trunk is a tapered, cone-shaped organ that protrudes forward, resembling the carrot nose
- `spider web anchor` — the spider web anchor is a tapered, cone-like structure that protrudes forward, similar to the carrot nose
- `beak tip` — the beak tip serves as a distinct landmark on the face of a bird, similar to the nose landmark on a human face
- `snout tip` — the snout tip is a prominent landmark on the face of an animal, analogous to the nose landmark on a human face
- `proboscis tip` — the proboscis tip is a specialized landmark on the face of an insect, functioning similarly to the nose landmark on a human face
- `beak tip` — the beak tip is inserted in the lower front of the head sphere, similar to the carrot nose
- `snout projection` — the snout projection is inserted in the lower front of the head sphere, similar to the carrot nose
- `nose horn` — the nose horn is inserted in the lower front of the head sphere, similar to the carrot nose
- `beak` — beak points forward as a primary feeding structure
- `spur` — spur extends forward for mechanical leverage
- `claw` — claw extends forward for grasping or digging
- `spider web` — spider web exhibits static as it remains fixed and does not move
- `barnacle` — barnacle exhibits static as it remains fixed to a surface without movement
- `moss` — moss exhibits static as it remains fixed in place without movement
- `lotus leaf` — the lotus leaf exhibits a smooth surface contact due to its hydrophobic properties and lack of visible seams
- `shark skin` — shark skin exhibits a smooth surface contact through its dermal denticles which create a seamless texture
- `waxy apple skin` — the waxy apple skin exhibits a smooth surface contact due to its continuous, seamless outer layer

## Santa Head（santa head）

部件：santa hat, beard, eyebrows

### 部件：santa hat（85.99s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：santa hat
- source_noun：santa head

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | soft conical cap with folded brim and pom-pom | conical mass above the head, pom ball at the tip | which concrete cross-domain entities exhibit this same relational property? | 0.93 |
| attr_02 | selected_part_function | head covering and festive marker | conical mass above the head, pom ball at the tip | which concrete cross-domain entities exhibit this same relational property? | 0.93 |
| attr_03 | attachment_logic | sits on top of the head and forehead | conical mass above the head, pom ball at the tip | which concrete cross-domain entities exhibit this same relational property? | 0.93 |
| attr_04 | articulation | non-articulated single piece | conical mass above the head, pom ball at the tip | which concrete cross-domain entities exhibit this same relational property? | 0.93 |
| attr_05 | orientation | upright conical orientation | conical mass above the head, pom ball at the tip | which concrete cross-domain entities exhibit this same relational property? | 0.93 |
| attr_06 | interface | smooth surface with folded brim | conical mass above the head, pom ball at the tip | which concrete cross-domain entities exhibit this same relational property? | 0.93 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（18 条）
- `conical hat` — conical hat has a similar conical shape with a folded brim and a decorative top
- `tulip shape` — tulip shape exhibits a conical form with a folded brim and a rounded top
- `pom-pom ornament` — pom-pom ornament features a soft conical shape with a folded brim and a pom-pom at the top
- `Christmas tree` — the Christmas tree serves as a festive marker and is often worn or displayed as a head covering in certain cultural contexts
- `Party hat` — the party hat is a head covering used as a festive marker in various celebrations
- `Bowler hat` — the bowler hat is a head covering that can serve as a festive marker in specific cultural or formal settings
- `traffic cone` — the traffic cone sits on top of the head and forehead in a similar spatial relationship
- `ice cream cone` — the ice cream cone sits on top of the head and forehead in a similar spatial relationship
- `chimney pot` — the chimney pot sits on top of the head and forehead in a similar spatial relationship
- `volcanic cone` — volcanic cone is a single piece structure formed by accumulated material
- `mushroom cap` — mushroom cap is a single piece structure formed by the fungal body
- `iceberg` — iceberg is a single piece structure formed by frozen water
- `pine cone` — pine cone exhibits an upright conical orientation with a pointed tip
- `volcano` — volcano exhibits an upright conical orientation with a peak at the top
- `chimney` — chimney exhibits an upright conical orientation with a pointed top
- `woven basket` — the woven basket has a smooth outer surface with a folded edge resembling the brim of a hat
- `ceramic vase` — the ceramic vase features a smooth surface with a folded rim that mimics the brim of a hat
- `metal cup` — the metal cup has a smooth exterior with a folded lip that resembles the brim of a hat

**getty_aat**（18 条）
- `conical shell` — conical shell exhibits a soft conical form with a folded edge and a rounded tip
- `feather tuft` — feather tuft exhibits a conical shape with a folded brim and a rounded tip
- `mushroom cap` — mushroom cap exhibits a soft conical form with a folded brim and a rounded tip
- `feathered headdress` — feathered headdress serves as a head covering and functions as a festive marker through its ornamental and symbolic presence
- `ceremonial crown` — ceremonial crown acts as a head covering and functions as a festive marker through its symbolic and decorative role
- `ornate turban` — ornate turban serves as a head covering and functions as a festive marker through its elaborate design and cultural significance
- `Crown` — A crown sits on top of the head and forehead, similar to a santa hat.
- `Helmet` — A helmet sits on top of the head and forehead, similar to a santa hat.
- `Cap` — A cap sits on top of the head and forehead, similar to a santa hat.
- `volcanic rock` — volcanic rock forms a single, non-articulated mass with a conical shape and a rounded tip
- `mushroom cap` — mushroom cap is a single, non-articulated structure with a conical body and a rounded top
- `iceberg` — iceberg is a single, non-articulated mass with a conical or rounded shape and a distinct tip
- `pine cone` — pine cone naturally exhibits an upright conical orientation
- `cherry blossom cluster` — cherry blossom cluster forms an upright conical orientation
- `volcanic cone` — volcanic cone exhibits an upright conical orientation
- `woven basket` — the woven basket has a smooth surface formed by folded strands that create a brim-like structure
- `oiled leather` — oiled leather exhibits a smooth surface with a folded edge that mimics the brim of a hat
- `folded paper` — folded paper creates a smooth surface with a folded edge that resembles the brim of a hat

**asknature**（18 条）
- `elephant trunk` — the elephant trunk has a conical shape with a flexible, folded structure at the base and a rounded tip resembling a pom-pom
- `seashell spiral` — the seashell spiral exhibits a conical shape with a folded, layered brim and a rounded, pom-pom-like tip
- `mushroom cap` — the mushroom cap has a conical shape with a folded, layered brim and a rounded, pom-pom-like tip
- `peacock feather` — peacock feather exhibits head covering and festive marker through its vibrant color and ornamental shape
- `mantis shrimp claw` — mantis shrimp claw exhibits head covering and festive marker through its striking color and unique morphology
- `butterfly wing` — butterfly wing exhibits head covering and festive marker through its iridescent color and intricate pattern
- `beaver dam` — the beaver dam sits on top of the riverbed and surrounding terrain, similar to how a santa hat sits on top of the head and forehead
- `ant hill` — the ant hill sits on top of the ground, much like a santa hat sits on top of the head and forehead
- `mushroom cap` — the mushroom cap sits on top of the stem, analogous to how a santa hat sits on top of the head and forehead
- `elephant tusk` — the elephant tusk is a single, non-articulated piece with a conical shape and a distinct tip
- `beaver tail` — the beaver tail is a single, non-articulated piece with a broad, flat shape and a distinct tip
- `mushroom cap` — the mushroom cap is a single, non-articulated piece with a conical or rounded shape and a distinct tip
- `pine cone` — pine cone exhibits an upright conical orientation with a pointed tip
- `elephant tusk` — elephant tusk has an upright conical orientation with a tapered end
- `volcanic cone` — volcanic cone displays an upright conical orientation with a central peak
- `butterfly wing` — butterfly wings have a smooth surface with folded edges that create a streamlined shape
- `lotus leaf` — lotus leaves have a smooth surface with a folded edge that helps repel water
- `eel skin` — eel skin has a smooth surface with a folded edge that allows for flexible movement

### 部件：beard（68.04s）

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
| attr_06 | interface | attached to the lower face | wraps around cheeks | which concrete cross-domain entities exhibit this same relational property? | 0.94 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（18 条）
- `volcanic rock` — volcanic rock forms bulky rounded masses due to cooling and solidification processes
- `mushroom cloud` — mushroom cloud exhibits a bulky rounded mass shape due to atmospheric expansion
- `lava dome` — lava dome forms a bulky rounded mass as molten rock cools and solidifies
- `lion mane` — lion mane defines the head silhouette through dense fur
- `elephant trunk` — elephant trunk defines the face silhouette through its prominent shape
- `horse tail` — horse tail defines the silhouette through its long, distinct shape
- `mohawk` — the mohawk covers the jaw and chin, wrapping around the mouth
- `ponytail` — the ponytail covers the jaw and chin, wrapping around the mouth
- `braid` — the braid covers the jaw and chin, wrapping around the mouth
- `horsehair` — horsehair spreads outward from the head in a similar directional manner
- `feather` — feather spreads outward from the body in a directional pattern
- `whisker` — whisker spreads outward from the face in a directional manner
- `cloud formation` — how the donor exhibits soft and flowing
- `frosted branch` — how the donor exhibits soft and flowing
- `feather cluster` — how the donor exhibits soft and flowing
- `whiskers` — whiskers are naturally attached to the lower face and wrap around the cheeks
- `moustache` — moustache is attached to the lower face and extends from the upper lip
- `beard` — beard is attached to the lower face and wraps around the cheeks

**getty_aat**（18 条）
- `volcanic rock` — volcanic rock forms bulky rounded masses through natural geological processes
- `burl wood` — burl wood exhibits bulky rounded masses as natural growth formations
- `lava flow` — lava flow creates bulky rounded masses through cooling and solidification
- `whiskers` — whiskers define the facial contours similar to facial hair
- `mohawk` — mohawk shapes the face silhouette through structured hair growth
- `beard` — beard outlines the face silhouette through dense hair growth
- `beard` — a beard covers the jaw and chin, wrapping around the mouth
- `mohawk` — a mohawk covers the jaw and chin, wrapping around the mouth
- `goatee` — a goatee covers the jaw and chin, wrapping around the mouth
- `feathered edge` — feathered edge spreads outward from the face
- `curled hair` — curled hair spreads outward from the face
- `flowing fringe` — flowing fringe spreads outward from the face
- `feathered edge` — feathered edge exhibits soft and flowing through its fine, layered structure
- `cloud formation` — cloud formation exhibits soft and flowing through its diffused, undulating shape
- `woven fabric` — woven fabric exhibits soft and flowing through its layered, flexible texture
- `chin strap` — chin strap is attached to the lower face to secure a mask or helmet
- `moustache` — moustache grows on the lower face and is attached to the facial skin
- `beard` — beard is attached to the lower face and grows from the chin and cheeks

**asknature**（18 条）
- `mussel shell` — mussel shell exhibits a bulky rounded mass as a protective structure
- `elephant tusk` — elephant tusk exhibits a bulky rounded mass as a functional appendage
- `barnacle cluster` — barnacle cluster exhibits a bulky rounded mass as a colonial growth
- `whale baleen` — whale baleen defines the shape of the whale's head and filters food from water
- `elephant trunk` — elephant trunk defines the shape of the elephant's face and serves as a versatile appendage
- `chameleon eyelid` — chameleon eyelid defines the shape of the eye and allows for rapid eye movement
- `beaver tail` — the beaver tail wraps around the body in a similar way to how a beard covers the jaw and chin
- `manta ray wing` — the manta ray wing extends over the body in a broad, covering manner similar to a beard
- `elephant trunk` — the elephant trunk wraps around the face and head in a covering manner akin to a beard
- `feathered edge` — feathered edge spreads outward from the central shaft
- `fan-shaped leaf` — fan-shaped leaf spreads outward from the petiole
- `radiating bristles` — radiating bristles spread outward from the base
- `whale fluke` — the whale fluke has a soft and flowing texture that moves with the water
- `elephant hide` — elephant hide has a soft and flowing surface that adapts to movement
- `moss growth` — moss growth has a soft and flowing appearance that spreads across surfaces
- `whale skin` — whale skin is attached to the lower face of the whale
- `manta ray gill slits` — manta ray gill slits are attached to the lower face of the manta ray
- `elephant trunk folds` — elephant trunk folds are attached to the lower face of the elephant

## Candle（candle）

部件：flame, wick, wax body

### 部件：flame（71.13s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：flame
- source_noun：candle

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | teardrop flame rising from the wick | small teardrop volume at the very top | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_02 | selected_part_function | emits light and heat | distinct from wax body | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_03 | attachment_logic | sits on top of the wick at the candle top | distinct from wax body | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_04 | orientation | vertical orientation | teardrop flame rising from the wick | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_05 | articulation | static form | distinct from wax body | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_06 | interface | top interface with wick | sits on top of the wick at the candle top | which concrete cross-domain entities exhibit this same relational property? | 0.9 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（18 条）
- `volcanic vent` — volcanic vent exhibits a teardrop shape with a rising flow from the base
- `lava flow` — lava flow forms a teardrop shape with a rising motion from the source
- `geyser jet` — geyser jet displays a teardrop shape with a rising flow from the ground
- `incandescent bulb` — incandescent bulb emits light and heat through electrical resistance
- `campfire` — campfire emits light and heat through combustion
- `glowing ember` — glowing ember emits light and heat through residual combustion
- `candle wick cap` — the candle wick cap sits on top of the wick at the candle top
- `lamp wick cover` — the lamp wick cover sits on top of the wick at the candle top
- `oil lamp wick sleeve` — the oil lamp wick sleeve sits on top of the wick at the candle top
- `spear` — the spear points vertically upward like a flame
- `pine tree` — the pine tree grows vertically upward from the ground
- `column` — the column stands vertically in architectural structures
- `granite boulder` — granite boulder exhibits static form through its unchanging, solid structure
- `iceberg` — iceberg maintains static form despite environmental changes
- `volcanic rock` — volcanic rock retains static form through geological stability
- `candle wick holder` — how the donor exhibits top interface with wick
- `lamp wick support` — how the donor exhibits top interface with wick
- `oil lamp wick rest` — how the donor exhibits top interface with wick

**getty_aat**（18 条）
- `volcanic vent` — the shape of a volcanic vent resembles a teardrop flame rising from the earth's surface
- `lava flow` — lava flows can form teardrop-like shapes as they rise from fissures
- `geyser spout` — a geyser spout exhibits a teardrop flame-like shape as it erupts from the ground
- `Flame` — Flame emits light and heat through combustion
- `Spark` — Spark emits light and heat through rapid oxidation
- `Incandescent` — Incandescent materials emit light and heat through high temperature
- `candle wick cap` — the candle wick cap sits on top of the wick at the candle top
- `lampshade trim` — the lampshade trim sits on top of the wick at the candle top
- `candle holder` — the candle holder sits on top of the wick at the candle top
- `spire` — spire exhibits vertical orientation through its elongated, upward-pointing form
- `column` — column exhibits vertical orientation through its straight, upright structure
- `needle` — needle exhibits vertical orientation through its slender, pointed shape
- `granite surface` — granite surface exhibits static form through its unchanging, solid appearance
- `ice formation` — ice formation exhibits static form through its frozen, unchanging structure
- `shell structure` — shell structure exhibits static form through its rigid, unchanging shape
- `wick holder` — the wick holder sits on top of the wick at the candle top
- `candle cap` — the candle cap sits on top of the wick at the candle top
- `burner ring` — the burner ring sits on top of the wick at the candle top

**asknature**（18 条）
- `volcanic vent` — the shape of a volcanic vent resembles a teardrop flame rising from the earth's surface
- `bioluminescent plankton` — bioluminescent plankton emit a teardrop-like light pattern rising from the water's surface
- `spider web dew` — dew forms a teardrop shape on spider webs, rising from the web's surface
- `bioluminescent bacteria` — bioluminescent bacteria emit light through chemical reactions and generate heat as a byproduct
- `volcanic vent` — volcanic vents emit intense heat and light due to geothermal activity
- `firefly` — fireflies emit light through bioluminescence and generate heat during the process
- `beard hair` — beard hair sits on top of the skin at the facial area
- `leaf tip` — leaf tip sits on top of the leaf at the terminal end
- `spore cap` — spore cap sits on top of the mushroom at the reproductive structure
- `vertical pinecone` — the pinecone's vertical orientation aligns with the flame's upward direction
- `upright fern frond` — the fern frond grows vertically, mirroring the flame's orientation
- `vertical bamboo stalk` — the bamboo stalk exhibits a natural vertical orientation
- `spider web` — spider web maintains a static form through structural tension and geometric arrangement
- `beaver dam` — beaver dam maintains a static form through interlocking materials and precise construction
- `termite mound` — termite mound maintains a static form through layered construction and natural stabilization
- `beaver dam` — beaver dam has a top interface with the water flow
- `termite mound` — termite mound has a top interface with the air flow
- `spider web` — spider web has a top interface with the wind

### 部件：wick（45.05s）

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

**wikidata**（12 条）
- `firewood` — how the donor exhibits thin vertical stalk
- `bamboo stalk` — how the donor exhibits thin vertical stalk
- `candle wick` — how the donor exhibits thin vertical stalk
- `wick` — how the donor exhibits conducts melted wax to the flame
- `candle wick` — how the donor exhibits conducts melted wax to the flame
- `burning wick` — how the donor exhibits conducts melted wax to the flame
- `candle wick` — the wick is embedded in the top center of the wax body
- `spindle` — the spindle is embedded in the top center of the wax body
- `core wire` — the core wire is embedded in the top center of the wax body
- `spine` — how the donor exhibits vertical alignment
- `flagpole` — how the donor exhibits vertical alignment
- `bamboo stalk` — how the donor exhibits vertical alignment

**getty_aat**（12 条）
- `spine` — how the donor exhibits thin vertical stalk
- `stem` — how the donor exhibits thin vertical stalk
- `column` — how the donor exhibits thin vertical stalk
- `wax channel` — how the donor exhibits conducts melted wax to the flame
- `fuel conduit` — how the donor exhibits conducts melted wax to the flame
- `melted wax path` — how the donor exhibits conducts melted wax to the flame
- `rivet` — a rivet is embedded in the top center of a metal structure, similar to how the wick is embedded in the wax body
- `handle` — a handle is embedded in the top center of a tool or object, analogous to the wick's placement in the wax body
- `cap` — a cap is embedded in the top center of a container or vessel, mirroring the wick's position in the wax body
- `columnar structure` — how the donor exhibits vertical alignment
- `spine` — how the donor exhibits vertical alignment
- `fibril` — how the donor exhibits vertical alignment

**asknature**（12 条）
- `spider silk strand` — how the donor exhibits thin vertical stalk
- `bamboo stalk` — how the donor exhibits thin vertical stalk
- `eel body` — how the donor exhibits thin vertical stalk
- `vein network` — vein network transports nutrients through a plant, similar to how a wick conducts melted wax to the flame
- `capillary action` — capillary action moves liquid through narrow spaces, analogous to how melted wax moves up a wick
- `spider silk` — spider silk efficiently transfers tension and movement, similar to how a wick transfers melted wax
- `beaver dam keystone` — the keystone in a beaver dam is embedded in the top center of the structure, providing structural stability
- `termite mound central chamber` — the central chamber in a termite mound is embedded in the top center of the mound, serving as the primary living space
- `spider web hub` — the hub of a spider web is embedded in the top center of the web, acting as the central point of attachment
- `spider web` — spider web exhibits vertical alignment through its radial symmetry and central hub structure
- `bamboo stalk` — bamboo stalk maintains vertical alignment through its hollow, fibrous structure
- `fern frond` — fern frond exhibits vertical alignment through its central vein and leaflet arrangement

## Sled（sled）

部件：runner, seat, side rail

### 部件：runner（68.88s）

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

**wikidata**（18 条）
- `spear tip` — spear tip is a long curved blade used in hunting
- `scimitar` — scimitar is a long curved blade used in combat
- `shovel blade` — shovel blade is a long curved blade used for digging
- `snowshoe` — snowshoe distributes weight over snow and allows directional movement
- `ice skate` — ice skate glides over ice and enables directional control
- `ski` — ski moves over snow and allows steering through edge control
- `upturned snout` — how the donor exhibits curving up at the front
- `upturned beak` — how the donor exhibits curving up at the front
- `upturned lip` — how the donor exhibits curving up at the front
- `ski edge` — how the donor exhibits horizontal alignment with the sled
- `ice skate blade` — how the donor exhibits horizontal alignment with the sled
- `snowboard edge` — how the donor exhibits horizontal alignment with the sled
- `humpback whale fluke` — the fluke has flexible leading edges that allow for efficient swimming
- `elephant trunk` — the trunk has flexible front segments for grasping and manipulating objects
- `snake fang` — the fang has a flexible tip for piercing and injecting venom
- `ice skate blade` — how the donor exhibits direct contact with snow
- `snowshoe frame` — how the donor exhibits direct contact with snow
- `ski wax` — how the donor exhibits direct contact with snow

**getty_aat**（18 条）
- `curved blade` — how the donor exhibits long curved blade
- `sickle blade` — how the donor exhibits long curved blade
- `hooked edge` — how the donor exhibits long curved blade
- `snowshoe` — snowshoe distributes weight over snow and allows directional movement
- `ice skate` — ice skate glides over ice and enables directional control
- `wheeled sled` — wheeled sled moves over snow and allows steering through directional force
- `upturned lip` — the upturned lip curves upward at the front edge
- `curved rim` — the curved rim exhibits a forward-curving front edge
- `upturned edge` — the upturned edge curves upward at the front
- `ice blade` — the ice blade aligns horizontally with the sled to facilitate movement
- `wooden rail` — the wooden rail maintains horizontal alignment with the sled for stability
- `metal track` — the metal track ensures horizontal alignment with the sled for guided motion
- `curved shell` — the curved shell exhibits a flexible front tip through its natural curvature and organic form
- `wavy edge` — the wavy edge demonstrates a flexible front tip through its undulating and fluid contour
- `bent metal` — the bent metal shows a flexible front tip through its malleable and contoured shape
- `ice skate blade` — the blade is in direct contact with snow during use
- `snowshoe frame` — the frame is in direct contact with snow for support
- `ski edge` — the edge is in direct contact with snow during movement

**asknature**（18 条）
- `whale flipper` — whale flipper exhibits a long curved blade-like structure for swimming
- `eel body` — eel body has a long curved blade-like shape for efficient movement
- `raptor claw` — raptor claw features a long curved blade-like structure for grasping
- `snowshoe hare foot` — the snowshoe hare foot slides over snow and steers by distributing weight and adapting to terrain
- `arctic fox paw` — the arctic fox paw slides over snow and steers by adjusting grip and pressure distribution
- `ice skate blade` — the ice skate blade slides over snow and steers by carving and applying lateral force
- `upturned beak` — the beak curves upward at the front, similar to the upturned front tips
- `curved wingtip` — the wingtip curves upward, mirroring the upturned front tips
- `upturned lip` — the lip curves upward at the front, resembling the upturned front tips
- `eel-like movement` — how the donor exhibits horizontal alignment with the sled
- `fish tail undulation` — how the donor exhibits horizontal alignment with the sled
- `snake-like sliding` — how the donor exhibits horizontal alignment with the sled
- `lotus leaf` — the lotus leaf has flexible edges that allow it to shed water efficiently
- `spider silk` — spider silk has flexible tips that allow for dynamic movement and web construction
- `eel` — the eel has flexible front tips that aid in its undulating motion through water
- `snowshoe` — how the donor exhibits direct contact with snow
- `ice skate` — how the donor exhibits direct contact with snow
- `wading foot` — how the donor exhibits direct contact with snow

### 部件：seat（61.98s）

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
| attr_06 | interface | direct contact with rider | supports the rider | which concrete cross-domain entities exhibit this same relational property? | 0.88 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（18 条）
- `stone slab` — how the donor exhibits flat horizontal platform
- `wooden deck` — how the donor exhibits flat horizontal platform
- `metal plate` — how the donor exhibits flat horizontal platform
- `horse saddle` — horse saddle provides support for the rider's body
- `bicycle seat` — bicycle seat supports the rider's weight and posture
- `motorcycle seat` — motorcycle seat supports the rider during riding
- `bridge deck` — the bridge deck spans across the top of the bridge structure
- `canoe hull` — the canoe hull spans across the top of the canoe frame
- `raft platform` — the raft platform spans across the top of the raft frame
- `railroad track` — how the donor exhibits horizontal
- `table surface` — how the donor exhibits horizontal
- `flooring` — how the donor exhibits horizontal
- `bridge pier` — bridge pier is fixed in position and spans across a structure
- `door frame` — door frame is fixed and spans across the doorway
- `window frame` — window frame is fixed and spans across the window opening
- `horseback` — how the donor exhibits direct contact with rider
- `racing saddle` — how the donor exhibits direct contact with rider
- `mountain bike seat` — how the donor exhibits direct contact with rider

**getty_aat**（18 条）
- `stone slab` — how the donor exhibits flat horizontal platform
- `wooden panel` — how the donor exhibits flat horizontal platform
- `metal plate` — how the donor exhibits flat horizontal platform
- `Seat Frame` — The seat frame provides structural support to the rider by forming the base of the seating arrangement.
- `Pedestal` — A pedestal supports the rider by providing a stable base for the seat or the rider's body.
- `Backrest` — The backrest supports the rider by offering structural reinforcement and comfort during use.
- `wooden plank` — the wooden plank spans across the top of the sled frame in a similar structural manner
- `metal rail` — the metal rail spans across the top of the sled frame in a similar structural manner
- `stone arch` — the stone arch spans across the top of the sled frame in a similar structural manner
- `Flat Surface` — how the donor exhibits horizontal
- `Sheet Metal` — how the donor exhibits horizontal
- `Wooden Plank` — how the donor exhibits horizontal
- `cast iron` — cast iron is fixed in place and does not move, similar to the fixed articulation of the seat
- `wooden dowel` — wooden dowel is fixed in position and provides a rigid connection, analogous to the fixed articulation of the seat
- `stone pillar` — stone pillar is fixed in location and remains immobile, mirroring the fixed articulation of the seat
- `horsehair` — horsehair provides direct contact with rider through its tactile and structural integration in materials like horsehair plaster
- `woven reed` — woven reed offers direct contact with rider through its flexible and interwoven physical structure
- `natural fiber` — natural fiber provides direct contact with rider through its inherent tactile and structural properties

**asknature**（18 条）
- `beaver dam` — how the donor exhibits flat horizontal platform
- `termite mound` — how the donor exhibits flat horizontal platform
- `mussel shell` — how the donor exhibits flat horizontal platform
- `spider web` — spider web provides structural support and stability for the spider's body and environment
- `termite mound` — termite mound supports the colony and provides structural integrity for the termites
- `beaver dam` — beaver dam supports water flow and provides structural stability for the beaver habitat
- `spider web` — spider web spans across the top of the sled frame by forming a continuous structure over a surface
- `beaver dam` — beaver dam spans across the top of the sled frame by creating a continuous barrier over a surface
- `termite mound` — termite mound spans across the top of the sled frame by forming a continuous structure over a surface
- `flat leaf` — how the donor exhibits horizontal
- `horizontal layer` — how the donor exhibits horizontal
- `flat shell` — how the donor exhibits horizontal
- `spider web` — spider web is fixed in place and spans across a structure
- `beaver dam` — beaver dam is fixed in place and spans across a waterway
- `termite mound` — termite mound is fixed in place and spans across the ground
- `spider web` — spider web provides direct contact with the environment through its fibrous structure
- `beaver dam` — beaver dam provides direct contact with water through its physical structure
- `termite mound` — termite mound provides direct contact with the surrounding soil through its porous structure

## Bell（bell）

部件：clapper, handle, bell body

### 部件：clapper（54.01s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：clapper
- source_noun：bell

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | small sphere | small sphere visible inside the open mouth | which concrete cross-domain entities exhibit this same relational property? | 0.86 |
| attr_02 | selected_part_function | strikes the body to produce sound | small sphere visible inside the open mouth | which concrete cross-domain entities exhibit this same relational property? | 0.86 |
| attr_03 | attachment_logic | suspended from the crown inside the body | small sphere visible inside the open mouth | which concrete cross-domain entities exhibit this same relational property? | 0.86 |
| attr_04 | articulation | free movement within the bell mouth | small sphere visible inside the open mouth | which concrete cross-domain entities exhibit this same relational property? | 0.86 |
| attr_05 | interface | contact with bell body for sound production | small sphere visible inside the open mouth | which concrete cross-domain entities exhibit this same relational property? | 0.86 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（15 条）
- `golf ball` — the golf ball contains a small sphere inside its core
- `marble` — the marble is a small sphere made of stone
- `boule` — the boule is a small sphere used in games
- `drumstick` — the drumstick strikes the drumhead to produce sound
- `hammer` — the hammer strikes the anvil to produce sound
- `mallet` — the mallet strikes the surface to produce sound
- `spider web` — the web is suspended from the spider's body inside its habitat
- `mushroom gill` — the gill is suspended from the mushroom's cap inside its structure
- `flower petal` — the petal is suspended from the flower's stem inside its bloom
- `sponge` — sponge allows fluid movement within its porous structure
- `moss` — moss exhibits free movement of water and air within its fibrous structure
- `coral` — coral allows for free movement of water and marine life within its branching structure
- `drumhead` — how the donor exhibits contact with bell body for sound production
- `tongue` — how the donor exhibits contact with bell body for sound production
- `vocal cord` — how the donor exhibits contact with bell body for sound production

**getty_aat**（15 条）
- `glass bead` — glass bead exhibits a small sphere shape
- `pearl` — pearl exhibits a small sphere shape
- `seed` — seed exhibits a small sphere shape
- `clapper` — the clapper strikes the body to produce sound
- `hammer` — the hammer strikes the body to produce sound
- `mallet` — the mallet strikes the body to produce sound
- `vein structure` — vein structure suspends within the body like a crown
- `spider web` — spider web suspends within the structure like a crown
- `cyst` — cyst suspends within the body like a crown
- `spherical bead` — the spherical bead allows free movement within the open structure
- `pearl` — the pearl can move freely within the open structure
- `seed` — the seed can move freely within the open structure
- `clapper` — the clapper makes contact with the bell body to produce sound
- `tongue` — the tongue contacts the bell body to generate sound
- `hammer` — the hammer contacts the bell body to produce sound

**asknature**（15 条）
- `bee hive cell` — bee hive cell contains small spherical chambers
- `pearl structure` — pearl structure forms small spherical layers
- `sponge pores` — sponge pores exhibit small spherical openings
- `whale call` — whale call strikes the water to produce sound
- `drum skin` — drum skin strikes the drum body to produce sound
- `bee wing` — bee wing strikes the air to produce sound
- `spider web silk` — spider web silk is suspended from the central hub inside the web structure
- `bee hive comb` — bee hive comb is suspended from the central frame inside the hive
- `mussel byssus thread` — mussel byssus thread is suspended from the central anchor inside the mussel's body
- `fish gill` — fish gill allows free movement of water through its structure
- `insect proboscis` — insect proboscis enables free movement of liquid through its hollow structure
- `bird beak` — bird beak allows free movement of food through its opening
- `whale call structure` — the whale call structure involves contact between specialized tissues that produce sound through vibration
- `cricket stridulation` — cricket stridulation involves contact between specialized body parts that produce sound through friction
- `frog vocal sac` — the frog vocal sac involves contact between the sac and surrounding tissues to produce sound

### 部件：handle（115.77s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：handle
- source_noun：bell

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | small loop or knob | loop/knob above the domed body | which concrete cross-domain entities exhibit this same relational property? | 0.82 |
| attr_02 | selected_part_function | holding and hanging point | loop/knob above the domed body | which concrete cross-domain entities exhibit this same relational property? | 0.82 |
| attr_03 | attachment_logic | attached to the crown of the bell body | loop/knob above the domed body | which concrete cross-domain entities exhibit this same relational property? | 0.82 |
| attr_04 | orientation | vertically aligned | loop/knob above the domed body | which concrete cross-domain entities exhibit this same relational property? | 0.82 |
| attr_05 | articulation | non-movable | loop/knob above the domed body | which concrete cross-domain entities exhibit this same relational property? | 0.82 |
| attr_06 | interface | smooth surface | loop/knob above the domed body | which concrete cross-domain entities exhibit this same relational property? | 0.82 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（18 条）
- `handle` — the handle has a small loop or knob above the domed body
- `spoon` — the spoon has a small loop or knob above the domed body
- `earring` — the earring has a small loop or knob above the domed body
- `hanger loop` — a hanger loop is a physical feature designed for holding and hanging garments
- `hook attachment` — a hook attachment serves as a holding and hanging point for objects
- `clasp mechanism` — a clasp mechanism functions as a holding and hanging point for securing items
- `bell handle` — the handle is attached to the crown of the bell body
- `cup handle` — the handle is attached to the crown of the cup body
- `jug handle` — the handle is attached to the crown of the jug body
- `spider web` — spider web exhibits vertically aligned strands
- `bamboo stalk` — bamboo stalk exhibits vertically aligned fibers
- `feather shaft` — feather shaft exhibits vertically aligned barbs
- `knob` — the knob remains fixed in place without movement
- `rivet` — the rivet is permanently fixed and cannot move
- `clasp` — the clasp is designed to stay in a fixed position
- `glass surface` — glass surface exhibits smoothness through its molecular structure and manufacturing process
- `polished stone` — polished stone achieves smoothness through grinding and polishing techniques
- `waxed wood` — waxed wood achieves smoothness through the application of a protective and smoothing wax layer

**getty_aat**（18 条）
- `knob handle` — the knob handle features a small loop or knob above the domed body
- `loop handle` — the loop handle features a small loop or knob above the domed body
- `knob ornament` — the knob ornament features a small loop or knob above the domed body
- `loop handle` — a loop handle serves as a holding and hanging point by providing a grip and attachment mechanism
- `knob attachment` — a knob attachment functions as a holding and hanging point by offering a secure grip and suspension feature
- `hanger loop` — a hanger loop acts as a holding and hanging point by enabling suspension and secure attachment
- `knob` — a knob is a protruding feature attached to the crown of a bell-like structure
- `loop` — a loop is a ring-like structure attached to the crown of a bell-like structure
- `handle` — a handle is a gripping feature attached to the crown of a bell-like structure
- `knob` — the knob is positioned above the domed body, exhibiting vertical alignment
- `spindle` — the spindle is aligned vertically within the structure
- `rivet` — the rivet is vertically aligned with the surrounding structure
- `knob` — knob remains fixed in place without movement
- `rivet` — rivet is permanently fixed in a structure
- `clasp` — clasp remains locked in position without movement
- `polished stone` — polished stone exhibits a smooth surface through grinding and polishing processes
- `glass surface` — glass surface is inherently smooth due to its molecular structure and manufacturing process
- `wax coating` — wax coating creates a smooth surface by filling in microscopic imperfections on the material

**asknature**（18 条）
- `spider web anchor` — the spider web anchor features a small loop or knob used for securing the web to surfaces
- `mussel foot` — the mussel foot has a small loop or knob structure for adhering to surfaces
- `beaver tail` — the beaver tail has a small loop or knob-like structure for gripping and manipulating objects
- `spider web anchor` — spider web anchor provides a secure holding and hanging point for prey or other structures
- `mussel foot` — mussel foot functions as a holding and hanging point for attachment to surfaces
- `beaver dam post` — beaver dam post serves as a holding and hanging point for structural support
- `spider web anchor` — the spider web anchor is attached to the crown of the web structure, similar to the attachment to the crown of the bell body
- `beaver dam keystone` — the beaver dam keystone is attached to the crown of the dam structure, similar to the attachment to the crown of the bell body
- `mussel byssus anchor` — the mussel byssus anchor is attached to the crown of the shell structure, similar to the attachment to the crown of the bell body
- `bee hive comb` — bee hive comb exhibits vertically aligned cells
- `bamboo stalk` — bamboo stalk has vertically aligned vascular bundles
- `termite mound` — termite mound has vertically aligned tunnels
- `clam shell` — clam shell has a non-movable hinge mechanism
- `beaver tail` — beaver tail has a non-movable attachment to the body
- `butterfly wing` — butterfly wing is non-movable once attached to the body
- `butterfly wing` — butterfly wings have a smooth, iridescent surface that reduces drag and enhances aerodynamics
- `lotus leaf` — lotus leaves have a smooth, hydrophobic surface that repels water and dirt
- `shark skin` — shark skin has a smooth, streamlined surface that reduces water resistance and improves swimming efficiency

## Wreath（wreath）

部件：foliage ring, berries, bow

### 部件：foliage ring（123.5s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：foliage ring
- source_noun：wreath

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | layered leaf texture around the loop | layered leaf texture around the loop | which concrete cross-domain entities exhibit this same relational property? | 0.95 |
| attr_02 | selected_part_function | structural ring and decorative body | dominant circular band, layered leaf texture around the loop | which concrete cross-domain entities exhibit this same relational property? | 0.95 |
| attr_03 | attachment_logic | continuous circular band forming the wreath | continuous circular band forming the wreath | which concrete cross-domain entities exhibit this same relational property? | 0.95 |
| attr_04 | orientation | circular loop aligned with the wreath's plane | continuous circular band forming the wreath | which concrete cross-domain entities exhibit this same relational property? | 0.95 |
| attr_05 | articulation | no articulation, continuous loop | continuous circular band forming the wreath | which concrete cross-domain entities exhibit this same relational property? | 0.95 |
| attr_06 | interface | smooth surface with layered leaf texture | layered leaf texture around the loop | which concrete cross-domain entities exhibit this same relational property? | 0.95 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（18 条）
- `bamboo bark` — bamboo bark exhibits layered leaf texture around the loop through its fibrous, concentric layers
- `tree bark` — tree bark exhibits layered leaf texture around the loop through its concentric, fibrous layers
- `cork surface` — cork surface exhibits layered leaf texture around the loop through its cellular, layered structure
- `coral ring` — coral ring forms a circular structure with layered textures resembling leaf patterns
- `bamboo ring` — bamboo ring creates a circular form with layered, textured segments that mimic leaf structures
- `seashell` — seashell exhibits a natural circular band with layered, textured surfaces resembling leaf patterns
- `hoop` — a hoop forms a continuous circular band around an object
- `bracelet` — a bracelet forms a continuous circular band around the wrist
- `necklace` — a necklace forms a continuous circular band around the neck
- `hoop` — a hoop forms a circular loop aligned with its plane
- `ring` — a ring forms a circular loop aligned with its plane
- `bracelet` — a bracelet forms a circular loop aligned with its plane
- `seashell edge` — how the donor exhibits no articulation, continuous loop
- `moss edge` — how the donor exhibits no articulation, continuous loop
- `lichen edge` — how the donor exhibits no articulation, continuous loop
- `bamboo bark` — bamboo bark exhibits a smooth surface with layered leaf texture through its natural fibrous structure
- `pine needle` — pine needle has a smooth surface with layered leaf texture due to its segmented, overlapping scales
- `oak flake` — oak flake displays a smooth surface with layered leaf texture through its thin, laminated cellular structure

**getty_aat**（18 条）
- `peacock feather` — peacock feather exhibits layered leaf texture around the loop through its iridescent, layered structure
- `bamboo sheath` — bamboo sheath exhibits layered leaf texture around the loop through its tightly wrapped, fibrous layers
- `moss layer` — moss layer exhibits layered leaf texture around the loop through its dense, overlapping growth pattern
- `braided reed` — the braided reed forms a circular band with layered texture around the loop, similar to the foliage ring's structural and decorative function
- `woven basket` — the woven basket creates a circular band with layered texture around the loop, mirroring the foliage ring's structural and decorative function
- `coiled wire` — the coiled wire forms a circular band with layered texture around the loop, analogous to the foliage ring's structural and decorative function
- `woven reed` — woven reed forms a continuous circular band through interlacing fibers
- `braided hair` — braided hair creates a continuous circular band through interwoven strands
- `seashell edge` — seashell edge exhibits a continuous circular band through natural curvature
- `spiral shell` — the spiral shell exhibits a circular loop aligned with its natural plane
- `ringed leaf` — the ringed leaf forms a circular loop aligned with its plane
- `circular coral` — the circular coral exhibits a circular loop aligned with its plane
- `seashell edge` — the continuous, unbroken edge of a seashell mimics the no articulation, continuous loop attribute
- `lichen growth` — lichen forms a continuous, unbroken growth pattern on surfaces, resembling the no articulation, continuous loop attribute
- `woven reed` — woven reed creates a continuous, unbroken loop without distinct articulation points
- `wax leaf` — wax leaf exhibits a smooth surface with layered leaf texture through its natural formation
- `bark layer` — bark layer exhibits a smooth surface with layered leaf texture through its natural stratification
- `shell surface` — shell surface exhibits a smooth surface with layered leaf texture through its natural concentric layers

**asknature**（18 条）
- `abalone shell layers` — abalone shell layers exhibit a layered texture that wraps around the shell's structure, similar to the layered leaf texture around the loop
- `bamboo vascular bundles` — bamboo vascular bundles form a layered, cylindrical structure that wraps around the stem, resembling the layered leaf texture around the loop
- `sphagnum moss layers` — sphagnum moss layers create a stacked, cylindrical texture that wraps around the moss's central axis, akin to the layered leaf texture around the loop
- `sea urchin spines` — the spines form a protective ring around the body, creating a structural and decorative pattern
- `mussel shell` — the shell forms a circular ring that encases the body, with intricate patterns that serve both structural and decorative purposes
- `bee hive` — the hexagonal cells form a ring-like structure around the hive's core, providing structural support and a decorative arrangement
- `seashell edge` — the edge of a seashell forms a continuous circular band around its perimeter
- `mushroom cap` — the cap of a mushroom forms a continuous circular band at its top
- `flower petal ring` — the petal ring of a flower forms a continuous circular band around the center
- `spiral shell` — the spiral shell forms a continuous circular loop aligned with its plane
- `mussel byssus` — the mussel byssus creates a circular loop aligned with the surface it adheres to
- `honeycomb cell` — the honeycomb cell forms a circular loop aligned with the plane of the structure
- `seashell edge` — how the donor exhibits no articulation, continuous loop
- `mussel shell` — how the donor exhibits no articulation, continuous loop
- `barnacle edge` — how the donor exhibits no articulation, continuous loop
- `butterfly wing` — butterfly wings have a smooth surface with layered microscopic structures that create a textured appearance
- `fish scale` — fish scales have a smooth surface with layered, overlapping structures that create a textured appearance
- `snake skin` — snake skin has a smooth surface with layered, overlapping scales that create a textured appearance

### 部件：berries（67.16s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：berries
- source_noun：wreath

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | small spheres clustered on the ring | small round bumps on the ring | which concrete cross-domain entities exhibit this same relational property? | 0.85 |
| attr_02 | selected_part_function | color accent and texture contrast | small round bumps on the ring | which concrete cross-domain entities exhibit this same relational property? | 0.85 |
| attr_03 | attachment_logic | scattered on the foliage ring surface | small round bumps on the ring | which concrete cross-domain entities exhibit this same relational property? | 0.85 |
| attr_04 | articulation | non-attached, surface-based | small round bumps on the ring | which concrete cross-domain entities exhibit this same relational property? | 0.85 |
| attr_05 | orientation | randomly distributed on the ring | small round bumps on the ring | which concrete cross-domain entities exhibit this same relational property? | 0.85 |
| attr_06 | interface | surface contact with foliage ring | small round bumps on the ring | which concrete cross-domain entities exhibit this same relational property? | 0.85 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（18 条）
- `pearl formation` — how the donor exhibits small spheres clustered on the ring
- `spherical coral` — how the donor exhibits small spheres clustered on the ring
- `clustered dew` — how the donor exhibits small spheres clustered on the ring
- `spongy bark` — spongy bark exhibits color accent and texture contrast through its rough, uneven surface and varied coloration
- `rough stone` — rough stone exhibits color accent and texture contrast through its uneven surface and varied mineral composition
- `pebbled glass` — pebbled glass exhibits color accent and texture contrast through its irregular surface and translucent coloration
- `lichen growth` — how the donor exhibits scattered on the foliage ring surface
- `moss patches` — how the donor exhibits scattered on the foliage ring surface
- `spore clusters` — how the donor exhibits scattered on the foliage ring surface
- `cracked paint` — cracked paint forms non-attached, surface-based patterns on surfaces
- `frost patterns` — frost patterns appear as non-attached, surface-based formations on surfaces
- `lichen growth` — lichen growth forms non-attached, surface-based colonies on surfaces
- `volcanic rock` — how the donor exhibits randomly distributed on the ring
- `tree bark` — how the donor exhibits randomly distributed on the ring
- `coral reef` — how the donor exhibits randomly distributed on the ring
- `rough bark` — rough bark exhibits surface contact with foliage ring through its textured outer layer
- `tree trunk` — tree trunk exhibits surface contact with foliage ring through its cylindrical outer surface
- `stone surface` — stone surface exhibits surface contact with foliage ring through its uneven natural texture

**getty_aat**（18 条）
- `pearl cluster` — pearl cluster exhibits small spheres clustered on the ring
- `beadwork pattern` — beadwork pattern exhibits small spheres clustered on the ring
- `coral formation` — coral formation exhibits small spheres clustered on the ring
- `moss growth` — moss growth creates color variation and adds a textured surface through organic patterns
- `rust patina` — rust patina introduces color variation and a rough, textured surface through oxidation
- `lichen coating` — lichen coating provides color variation and a textured surface through biological growth
- `Lichen Growth` — Lichen Growth exhibits scattered distribution on surfaces similar to the foliage ring surface.
- `Fungal Spores` — Fungal Spores are scattered on surfaces in a manner analogous to the foliage ring surface.
- `Salt Crust` — Salt Crust forms scattered deposits on surfaces, similar to the foliage ring surface.
- `scale patterns` — scale patterns are non-attached, surface-based features found on natural and artificial surfaces
- `bloom finish` — bloom finish is a non-attached, surface-based texture created by mineral deposits on surfaces
- `frosting` — frosting is a non-attached, surface-based texture formed by a thin layer of ice or mineral deposits
- `Stippling` — Stippling involves small dots or bumps randomly distributed across a surface, similar to the described pattern.
- `Pitting` — Pitting refers to small, random depressions or bumps on a surface, akin to the described distribution.
- `Cratering` — Cratering involves small, randomly distributed depressions or pits on a surface, matching the described pattern.
- `Bark Texture` — Bark Texture exhibits surface contact with foliage ring through small round bumps on the ring
- `Rustic Finish` — Rustic Finish exhibits surface contact with foliage ring through small round bumps on the ring
- `Foliage Ring` — Foliage Ring exhibits surface contact with foliage ring through small round bumps on the ring

**asknature**（18 条）
- `bee hive cells` — bee hive cells exhibit small spheres clustered on the ring
- `sea urchin spines` — sea urchin spines exhibit small spheres clustered on the ring
- `moss spore clusters` — moss spore clusters exhibit small spheres clustered on the ring
- `peacock feather` — peacock feather exhibits color accent and texture contrast through iridescent colors and fine barbed structures
- `butterfly wing` — butterfly wing exhibits color accent and texture contrast through vibrant colors and intricate scale patterns
- `spider web` — spider web exhibits color accent and texture contrast through silvery threads and complex geometric patterns
- `spider silk strands` — spider silk strands are scattered across the web surface in a pattern similar to scattered bumps on the foliage ring
- `moss growth patterns` — moss growth patterns are scattered across the surface of a substrate, akin to scattered bumps on the foliage ring
- `lichen patches` — lichen patches are scattered across the surface of a rock or tree, similar to scattered bumps on the foliage ring
- `spider web` — spider web features non-attached, surface-based structures that adhere through surface tension and van der Waals forces
- `lotus leaf` — lotus leaf has non-attached, surface-based microstructures that repel water through a hydrophobic surface
- `gecko foot` — gecko foot has non-attached, surface-based setae that adhere through van der Waals forces without direct attachment
- `spider web` — spider web has randomly distributed silk strands on its surface
- `barnacle clusters` — barnacle clusters are randomly distributed on the surface of a shell
- `lichen growth` — lichen growth appears randomly distributed on tree bark
- `Velvet Leaf Surface` — The velvet texture of the leaf surface creates a soft, textured contact with surrounding foliage.
- `Corky Stem Nodes` — The corky nodes on the stem provide a textured surface that interacts with adjacent foliage.
- `Furrowed Bark` — The furrowed texture of bark creates a surface that makes contact with surrounding plant structures.

## Gift Bag（gift bag）

部件：handle, bag body, folded top

### 部件：handle（84.4s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：handle
- source_noun：gift bag

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | two ribbon loops rising from the top edges | two loops above the bag opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_02 | selected_part_function | carrying grip | attached to the folded top of the bag | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_03 | attachment_logic | attached to the folded top of the bag | attached to the folded top of the bag | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_04 | orientation | horizontal placement | two loops above the bag opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_05 | articulation | non-articulated | two loops above the bag opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_06 | interface | loop interface | two loops above the bag opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（18 条）
- `sling bag handle` — how the donor exhibits two ribbon loops rising from the top edges
- `belt buckle` — how the donor exhibits two ribbon loops rising from the top edges
- `handlebar grips` — how the donor exhibits two ribbon loops rising from the top edges
- `handlebar` — how the donor exhibits carrying grip
- `grip pad` — how the donor exhibits carrying grip
- `claw hand` — how the donor exhibits carrying grip
- `zipper` — a zipper is attached to the folded top of a bag to secure it
- `handle` — a handle is attached to the folded top of a bag for carrying
- `strap` — a strap is attached to the folded top of a bag to provide support
- `horizontal fence` — how the donor exhibits horizontal placement
- `horizontal shelf` — how the donor exhibits horizontal placement
- `horizontal rail` — how the donor exhibits horizontal placement
- `ceramic vase` — the ceramic vase has a single continuous form without separate articulated parts
- `stone pillar` — the stone pillar is a single solid structure without articulated components
- `wooden beam` — the wooden beam is a single piece without articulated joints or segments
- `chain link fence` — how the donor exhibits loop interface
- `wire mesh` — how the donor exhibits loop interface
- `knit fabric` — how the donor exhibits loop interface

**getty_aat**（18 条）
- `twisted metal bands` — how the donor exhibits two ribbon loops rising from the top edges
- `braided fiber strands` — how the donor exhibits two ribbon loops rising from the top edges
- `woven reed strips` — how the donor exhibits two ribbon loops rising from the top edges
- `handle` — the handle provides a carrying grip by being attached to the folded top of the bag
- `loop` — the loop offers a carrying grip by being attached to the folded top of the bag
- `strap` — the strap provides a carrying grip by being attached to the folded top of the bag
- `handle` — the handle is attached to the folded top of the bag
- `strap` — the strap is attached to the folded top of the bag
- `loop` — the loop is attached to the folded top of the bag
- `horizontal bar` — the horizontal bar is positioned parallel to the ground, similar to the horizontal placement of the loops above the bag opening
- `horizontal seam` — the horizontal seam runs parallel to the ground, mirroring the horizontal placement of the loops above the bag opening
- `horizontal strip` — the horizontal strip is aligned parallel to the ground, analogous to the horizontal placement of the loops above the bag opening
- `solid base` — the solid base lacks movable joints or separable parts
- `unbroken surface` — the unbroken surface lacks segmented or detachable elements
- `integral form` — the integral form is a single, unified structure without separable components
- `metal loop` — metal loop forms a loop interface through its physical shape and function
- `chain link` — chain link creates a loop interface through its interlocking structure
- `spiral form` — spiral form exhibits a loop interface through its continuous curvature

**asknature**（18 条）
- `spider web anchor points` — how the donor exhibits two ribbon loops rising from the top edges
- `mussel foot anchors` — how the donor exhibits two ribbon loops rising from the top edges
- `antennae attachment points` — how the donor exhibits two ribbon loops rising from the top edges
- `chimpanzee hand` — chimpanzee hand provides a strong, flexible grip for carrying objects
- `elephant trunk` — elephant trunk can grasp and carry objects with precision
- `mussel foot` — mussel foot adheres and grips surfaces for secure attachment
- `spider web silk` — spider web silk is attached to the top of the web structure, similar to how the handle is attached to the folded top of the bag
- `beaver tail` — beaver tail is attached to the top of the body, analogous to the handle being attached to the folded top of the bag
- `mussel byssus` — mussel byssus is attached to the top of the shell, mirroring the handle's attachment to the folded top of the bag
- `antennae arrangement` — how the donor exhibits horizontal placement
- `leaf vein pattern` — how the donor exhibits horizontal placement
- `spider web layout` — how the donor exhibits horizontal placement
- `spider web` — spider web lacks articulated joints and maintains a continuous structure
- `bark texture` — bark texture is a continuous surface without articulated segments
- `cell membrane` — cell membrane is a continuous, non-articulated layer surrounding a cell
- `spider web` — spider web has interconnected loops that create a networked interface
- `mussel byssus` — mussel byssus features interlocking loops for secure attachment
- `leaf venation` — leaf venation forms a loop-based network for transport and support

### 部件：bag body（105.61s）

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
| attr_06 | interface | smooth surface with no additional interface elements | dominant vertical container volume | which concrete cross-domain entities exhibit this same relational property? | 0.95 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（18 条）
- `volcanic cone` — volcanic cone exhibits a tall box-like body with a tapered bottom
- `mushroom cap` — mushroom cap exhibits a tall box-like body with a tapered bottom
- `iceberg` — iceberg exhibits a tall box-like body with a tapered bottom
- `mushroom cap` — how the donor exhibits holds contents
- `pinecone` — how the donor exhibits holds contents
- `bottle` — how the donor exhibits holds contents
- `human torso` — the human torso occupies the main volume between the upper torso and lower torso, analogous to the main volume between top fold and base
- `tree trunk` — the tree trunk represents the main volume between the upper branches and lower roots, analogous to the main volume between top fold and base
- `mountain range` — the mountain range occupies the main volume between the upper peaks and lower valleys, analogous to the main volume between top fold and base
- `column` — how the donor exhibits vertical
- `tree trunk` — how the donor exhibits vertical
- `spire` — how the donor exhibits vertical
- `Granite Rock` — Granite Rock exhibits a non-articulated structure with a dominant vertical container volume.
- `Ceramic Vessel` — Ceramic Vessel exhibits a non-articulated form with a dominant vertical container volume.
- `Wooden Log` — Wooden Log exhibits a non-articulated structure with a dominant vertical container volume.
- `glass surface` — glass surface exhibits a smooth surface with no additional interface elements due to its homogeneous material composition
- `polished stone` — polished stone exhibits a smooth surface with no additional interface elements after mechanical refinement
- `wax coating` — wax coating exhibits a smooth surface with no additional interface elements through its viscous, uniform application

**getty_aat**（18 条）
- `tapered vase` — the tapered vase exhibits a tall box-like body with a tapered bottom
- `hourglass shape` — the hourglass shape exhibits a tall box-like body with a tapered bottom
- `spindle form` — the spindle form exhibits a tall box-like body with a tapered bottom
- `Ceramic Vessel` — A ceramic vessel is a container designed to hold contents, similar to the bag body's function.
- `Wooden Crate` — A wooden crate is a container designed to hold contents, similar to the bag body's function.
- `Metal Canister` — A metal canister is a container designed to hold contents, similar to the bag body's function.
- `core section` — the core section represents the central volume between the upper and lower parts of a structure
- `central body` — the central body occupies the main volume between the upper and lower sections of an object
- `main chamber` — the main chamber is the primary volume between the upper and lower parts of a structure
- `column` — column exhibits vertical through its elongated, upright form
- `tree trunk` — tree trunk exhibits vertical through its upright growth pattern
- `spire` — spire exhibits vertical through its pointed, upward orientation
- `Solid Form` — Solid Form lacks movable joints or separable parts, exhibiting non-articulated structure.
- `Integral Construction` — Integral Construction refers to a unified, unbroken form without detachable components, exhibiting non-articulated.
- `Monolithic Structure` — Monolithic Structure is a single, continuous unit without articulation or separable parts.
- `polished stone` — polished stone exhibits a smooth surface with no additional interface elements through a uniform, reflective finish
- `glass surface` — glass surface exhibits a smooth surface with no additional interface elements through its transparent, non-porous nature
- `wax coating` — wax coating exhibits a smooth surface with no additional interface elements through its even, glossy application

**asknature**（18 条）
- `beaver dam` — beaver dam has a tall, box-like structure with a tapered base for stability
- `termite mound` — termite mound exhibits a tall, box-like shape with a tapered bottom for structural efficiency
- `mussel shell` — mussel shell has a tall, box-like body with a tapered bottom for streamlined function
- `bee hive` — bee hive holds honey and brood in a structured, vertical arrangement
- `termite mound` — termite mound holds colony and nutrients in a vertical, compartmentalized structure
- `mushroom cap` — mushroom cap holds spores and protects them in a cup-like, vertical form
- `spider web` — the central web structure forms the main volume between the upper and lower parts of the web
- `beaver dam` — the central core of the dam forms the main volume between the upper and lower sections
- `termite mound` — the central chamber of the mound forms the main volume between the upper and lower sections
- `vertical tree trunk` — the trunk grows vertically from the base
- `vertical bamboo stalk` — the stalk maintains a vertical orientation
- `vertical pine cone` — the cone grows vertically from the branch
- `spider web` — spider web maintains a non-articulated structure with continuous fibrous strands
- `beaver dam` — beaver dam forms a non-articulated, cohesive structure with interlocking logs
- `termite mound` — termite mound exhibits a non-articulated, unified structure with interconnected chambers
- `lotus leaf` — the lotus leaf exhibits a smooth surface with no additional interface elements due to its hydrophobic properties
- `shark skin` — shark skin has a smooth surface with no additional interface elements, optimized for hydrodynamic efficiency
- `waxy apple skin` — the waxy apple skin exhibits a smooth surface with no additional interface elements, providing a protective barrier

## Sock（sock）

部件：cuff, heel, toe

### 部件：cuff（68.12s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：cuff
- source_noun：sock

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | ribbed cylindrical band | ribbed band at the opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_02 | selected_part_function | holds the sock on the leg | ribbed band at the opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_03 | attachment_logic | attached to the top edge of the leg tube | ribbed band at the opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_04 | orientation | horizontal band around the opening | ribbed band at the opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_05 | articulation | non-articulated single band | ribbed band at the opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |
| attr_06 | interface | smooth interface with the leg tube | ribbed band at the opening | which concrete cross-domain entities exhibit this same relational property? | 0.88 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（18 条）
- `ribbed pipe` — ribbed pipe exhibits a cylindrical shape with ribbed texture
- `ribbed barrel` — ribbed barrel exhibits a cylindrical shape with ribbed texture
- `ribbed cylinder` — ribbed cylinder exhibits a cylindrical shape with ribbed texture
- `ankle band` — a band around the ankle that secures the sock in place
- `waistband` — a band around the waist that secures clothing in place
- `collar` — a band around the neck that secures a shirt in place
- `ribbed band` — the ribbed band is attached to the top edge of the leg tube
- `collar band` — the collar band is attached to the top edge of the leg tube
- `waistband` — the waistband is attached to the top edge of the leg tube
- `belt buckle` — the belt buckle forms a horizontal band around the opening of the belt loop
- `collar band` — the collar band forms a horizontal band around the opening of the collar
- `waistband` — the waistband forms a horizontal band around the opening of the pants
- `ribbed band` — the ribbed band exhibits a non-articulated single band structure at its opening
- `wristband` — the wristband exhibits a non-articulated single band structure around the wrist
- `necklace` — the necklace exhibits a non-articulated single band structure around the neck
- `seamless knit` — seamless knit provides a smooth interface with the leg tube by eliminating seams and creating a continuous surface
- `latex coating` — latex coating creates a smooth interface with the leg tube by forming a continuous, flexible layer
- `silicone seal` — silicone seal ensures a smooth interface with the leg tube by forming a flexible, continuous bond

**getty_aat**（18 条）
- `ribbed cylinder` — a ribbed cylinder exhibits a cylindrical form with raised ridges, similar to the ribbed cylindrical band
- `ribbed tube` — a ribbed tube has a cylindrical shape with raised ridges, matching the ribbed cylindrical band
- `ribbed shell` — a ribbed shell has a cylindrical or curved shape with raised ridges, analogous to the ribbed cylindrical band
- `ribbed band` — the ribbed band functions to hold the sock on the leg by creating a snug fit
- `elasticated edge` — the elastically stretched edge functions to hold the sock on the leg by providing a secure fit
- `woven loop` — the woven loop functions to hold the sock on the leg by creating a secure attachment point
- `ribbed band` — the ribbed band is attached to the top edge of the leg tube, similar to the cited attribute
- `cuff edge` — the cuff edge is attached to the top edge of the leg tube, similar to the cited attribute
- `wristband` — the wristband is attached to the top edge of the leg tube, similar to the cited attribute
- `ribbed band` — the donor exhibits a horizontal band around the opening with a ribbed texture
- `collar band` — the donor exhibits a horizontal band around the opening, similar to a collar
- `wristband` — the donor exhibits a horizontal band around the opening, similar to a wristband
- `ribbed band` — the donor exhibits a single band with a ribbed texture
- `woven cord` — the donor exhibits a single band formed through weaving
- `natural ridge` — the donor exhibits a single band formed by natural ridges
- `smooth seam` — a smooth seam provides a seamless interface between two surfaces, similar to the smooth interface with the leg tube
- `glazed surface` — a glazed surface exhibits a smooth interface, analogous to the smooth interface with the leg tube
- `wet sand` — wet sand forms a smooth interface when compacted, similar to the smooth interface with the leg tube

**asknature**（18 条）
- `mussel shell` — mussel shell exhibits a ribbed cylindrical band structure for gripping surfaces
- `snake scale` — snake scale features a ribbed cylindrical band pattern for enhanced grip and friction
- `bee hive cell` — bee hive cell has a ribbed cylindrical band structure for structural reinforcement
- `spider web anchor` — spider web anchor holds the web in place on the leg
- `beetle wing clamp` — beetle wing clamp holds the wing on the leg
- `mussel foot grip` — mussel foot grip holds the foot on the leg
- `spider webbing` — spider webbing attaches to the top edge of the leg tube-like structure by forming a secure, edge-anchored network
- `beaver dam` — beaver dam attaches to the top edge of the leg tube-like structure by forming a reinforced, edge-anchored barrier
- `mussel byssus` — mussel byssus attaches to the top edge of the leg tube-like structure by forming a fibrous, edge-anchored attachment
- `seashell lip` — the seashell lip forms a horizontal band around the opening of the shell
- `flower petal rim` — the flower petal rim creates a horizontal band around the opening of the flower
- `insect wing margin` — the insect wing margin forms a horizontal band around the opening of the wing
- `spider web` — the spider web forms a non-articulated single band that spans between points, similar to a cuff
- `eel skin` — eel skin has a non-articulated single band-like structure that runs along its length
- `mussel byssus` — the mussel byssus forms a non-articulated single band of threads for attachment
- `lotus leaf` — the lotus leaf exhibits a smooth interface with water due to its hydrophobic surface
- `beaver tail` — the beaver tail has a smooth interface with water as it moves through it
- `shark skin` — shark skin has a smooth interface with water due to its streamlined texture

### 部件：heel（63.19s）

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

**wikidata**（18 条）
- `river meander` — the curved path of a river exhibits a rounded bend similar to the foot tube
- `oak branch` — the natural curvature of an oak branch forms a rounded bend
- `wave crest` — the top of a wave forms a rounded bend in the water surface
- `shoelace` — shoelace wraps the heel to secure the foot in the shoe
- `ankle wrap` — ankle wrap wraps the heel to provide support and compression
- `bandage` — bandage wraps the heel to cover and protect wounds or injuries
- `spoon handle` — the spoon handle exhibits a rear corner similar to the foot tube
- `bottle neck` — the bottle neck exhibits a rear corner similar to the foot tube
- `door hinge` — the door hinge exhibits a rear corner similar to the foot tube
- `spine` — the spine exhibits vertical alignment through its central axis
- `tree trunk` — the tree trunk exhibits vertical alignment through its central axis
- `column` — the column exhibits vertical alignment through its central axis
- `snake skin` — snake skin exhibits a flexible bend through its natural undulating structure
- `eel body` — eel body exhibits a flexible bend through its elongated, sinuous form
- `willow branch` — willow branch exhibits a flexible bend through its naturally curved, supple structure
- `oceanic trench` — oceanic trenches exhibit seamless connection between tectonic plates
- `vascular system` — vascular systems exhibit seamless connection between capillaries and organs
- `spider silk` — spider silk exhibits seamless connection between fibrous strands

**getty_aat**（18 条）
- `shell curve` — the natural curvature of a shell mimics the rounded bend found in the foot tube
- `wave contour` — the smooth, flowing curve of a wave exhibits a rounded bend similar to the foot tube
- `bark ridge` — the rounded ridges on tree bark display a similar bend shape to the foot tube
- `spider web` — spider web wraps the heel area with a delicate, intricate pattern
- `moss growth` — moss growth wraps the heel area with a natural, clinging texture
- `tree bark` — tree bark wraps the heel area with a textured, layered surface
- `spoon handle` — the spoon handle exhibits a rear corner similar to the foot tube's rear corner
- `bottle neck` — the bottle neck exhibits a rear corner similar to the foot tube's rear corner
- `spider leg` — the spider leg exhibits a rear corner similar to the foot tube's rear corner
- `spine` — the spine exhibits vertical alignment through its central, upright structure
- `column` — the column exhibits vertical alignment through its straight, upright form
- `trunk` — the trunk exhibits vertical alignment through its central, upright structure
- `bent reed` — the natural curvature of reeds allows for flexible bending
- `woven willow` — the pliant nature of willow enables flexible bending in weaving
- `curved bamboo` — bamboo's inherent flexibility allows for curved, bendable structures
- `smooth junction` — smooth junctions connect parts without visible seams or breaks
- `continuous flow` — continuous flow describes a seamless transition between connected elements
- `integral bond` — integral bond refers to a connection that is unified and inseparable

**asknature**（18 条）
- `butterfly wing edge` — the edge of a butterfly wing exhibits a rounded bend similar to the foot tube's shape
- `shell spiral` — the spiral of a shell features a rounded bend that mirrors the foot tube's geometry
- `river meander` — a river meander forms a rounded bend that resembles the foot tube's shape
- `spider web` — spider web wraps around the leg to provide structural support and protection
- `mussel byssus` — mussel byssus wraps around the shell to anchor the mussel to surfaces
- `eel skin` — eel skin wraps around the body to provide flexibility and protection
- `spider web anchor` — spider web anchor exhibits a rear corner-like structure where the web attaches to the frame
- `beaver tail notch` — beaver tail notch functions as a rear corner for attaching to the body
- `crab claw grip` — crab claw grip features a rear corner for securing to surfaces
- `spider web` — spider web exhibits vertical alignment through its radial symmetry and structural geometry
- `beaver dam` — beaver dam exhibits vertical alignment through its layered, stacked construction
- `termite mound` — termite mound exhibits vertical alignment through its conical shape and internal structural organization
- `spider silk` — spider silk exhibits a flexible bend through its protein structure
- `eel body` — eel body exhibits a flexible bend through its undulating motion
- `lotus leaf` — lotus leaf exhibits a flexible bend through its waxy surface structure
- `spider web silk` — spider web silk connects structural elements with minimal visible seams
- `mussel foot` — mussel foot adheres to surfaces with a seamless interface
- `beaver dam` — beaver dam connects materials with a seamless interlocking structure

## Croissant（croissant）

部件：ridge, crescent tip, layered body

### 部件：ridge（64.73s）

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

**wikidata**（18 条）
- `moon surface` — moon surface exhibits raised crescent ridges through lunar topography
- `wave pattern` — wave pattern exhibits raised crescent ridges through fluid dynamics
- `spider web` — spider web exhibits raised crescent ridges through structural reinforcement
- `basalt column` — basalt columns exhibit lamination visual and texture through layered rock formations
- `tree bark` — tree bark exhibits lamination visual and texture through layered skin-like structures
- `ostrich eggshell` — ostrich eggshell exhibits lamination visual and texture through layered crystalline structures
- `volcanic rock` — how the donor exhibits concentric arcs on the upper surface
- `tree rings` — how the donor exhibits concentric arcs on the upper surface
- `spider web` — how the donor exhibits concentric arcs on the upper surface
- `striped fabric` — how the donor exhibits horizontal alignment across the top
- `layered paint` — how the donor exhibits horizontal alignment across the top
- `woven basket` — how the donor exhibits horizontal alignment across the top
- `volcanic rock` — volcanic rock exhibits continuous surface segment through its layered and undulating formations
- `woven basket` — woven basket exhibits continuous surface segment through its interlaced and flowing patterns
- `tree bark` — tree bark exhibits continuous surface segment through its textured and undulating ridges
- `roughened bark` — how the donor exhibits textured surface interaction
- `corrugated metal` — how the donor exhibits textured surface interaction
- `knurled handle` — how the donor exhibits textured surface interaction

**getty_aat**（18 条）
- `scaly skin` — scaly skin exhibits raised crescent ridges through overlapping scales
- `spiny surface` — spiny surface exhibits raised crescent ridges through sharp, curved projections
- `wavy bark` — wavy bark exhibits raised crescent ridges through undulating, curved patterns
- `layered bark` — layered bark exhibits lamination visual and texture through its natural stratified surface
- `sedimentary rock` — sedimentary rock exhibits lamination visual and texture through its layered mineral composition
- `fish scale` — fish scale exhibits lamination visual and texture through its overlapping, layered structure
- `volcanic rock` — volcanic rock exhibits concentric arcs on the upper surface through natural layering and cooling patterns
- `tree rings` — tree rings exhibit concentric arcs on the upper surface through annual growth patterns
- `shell patterns` — shell patterns exhibit concentric arcs on the upper surface through natural growth and formation
- `wave pattern` — how the donor exhibits horizontal alignment across the top
- `striped fabric` — how the donor exhibits horizontal alignment across the top
- `layered rock` — how the donor exhibits horizontal alignment across the top
- `wavy surface` — wavy surface exhibits continuous surface segment through undulating patterns
- `ridged texture` — ridged texture exhibits continuous surface segment through parallel raised bands
- `grooved surface` — grooved surface exhibits continuous surface segment through parallel recessed lines
- `knurled finish` — the raised ridges create a tactile pattern that interacts with surfaces
- `ribbed surface` — parallel raised bands create a tactile interaction with surfaces
- `grooved pattern` — the grooves create a tactile interaction with surfaces

**asknature**（18 条）
- `spider web patterns` — spider web patterns exhibit raised crescent ridges through their radial and spiral structural geometry
- `butterfly wing veins` — butterfly wing veins form raised crescent ridges through their intricate vascular network
- `mussel shell ridges` — mussel shell ridges display raised crescent ridges through their layered calcified structure
- `layered bark` — layered bark exhibits lamination visual and texture through its distinct, parallel ridges and textures
- `fish scale` — fish scale exhibits lamination visual and texture through its overlapping, raised, and patterned surface
- `feather barb` — feather barb exhibits lamination visual and texture through its segmented, parallel, and textured structure
- `spider web` — spider web exhibits concentric arcs on the upper surface through its radial and spiral thread patterns
- `lotus leaf` — lotus leaf exhibits concentric arcs on the upper surface through its waxy, curved microstructures
- `barnacle shell` — barnacle shell exhibits concentric arcs on the upper surface through its layered, curved calcified structures
- `layered bark` — how the donor exhibits horizontal alignment across the top
- `striped fish` — how the donor exhibits horizontal alignment across the top
- `woven reed` — how the donor exhibits horizontal alignment across the top
- `whale skin` — whale skin exhibits continuous surface segment through its smooth, unbroken texture
- `butterfly wing` — butterfly wing exhibits continuous surface segment through its seamless, curved surface
- `snake scale` — snake scale exhibits continuous surface segment through its elongated, connected pattern
- `spider web` — spider web exhibits textured surface interaction through its intricate, raised, and patterned structure
- `barnacle shell` — barnacle shell exhibits textured surface interaction through its ridged and raised surface patterns
- `moss carpet` — moss carpet exhibits textured surface interaction through its uneven, raised, and fibrous surface

### 部件：crescent tip（65.55s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：crescent tip
- source_noun：croissant

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | tapered pointed ends curving inward | two tapered inward-curving tips | which concrete cross-domain entities exhibit this same relational property? | 0.87 |
| attr_02 | selected_part_function | defines the crescent silhouette | two tapered inward-curving tips | which concrete cross-domain entities exhibit this same relational property? | 0.87 |
| attr_03 | attachment_logic | two ends of the crescent body | two tapered inward-curving tips | which concrete cross-domain entities exhibit this same relational property? | 0.87 |
| attr_04 | orientation | asymmetrically curved | two tapered inward-curving tips | which concrete cross-domain entities exhibit this same relational property? | 0.87 |
| attr_05 | articulation | connected to the main body | two tapered inward-curving tips | which concrete cross-domain entities exhibit this same relational property? | 0.87 |
| attr_06 | interface | smooth and continuous | two tapered inward-curving tips | which concrete cross-domain entities exhibit this same relational property? | 0.87 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（18 条）
- `arrowhead` — how the donor exhibits tapered pointed ends curving inward
- `scorpion tail` — how the donor exhibits tapered pointed ends curving inward
- `spider fang` — how the donor exhibits tapered pointed ends curving inward
- `moon phase` — the crescent shape of the moon phase mirrors the crescent silhouette defined by two inward-curving tips
- `shell valve` — the shell valve exhibits a crescent silhouette formed by two inward-curving tips
- `eyelid fold` — the eyelid fold forms a crescent silhouette with two inward-curving tips
- `arrowhead` — how the donor exhibits two ends of the crescent body
- `scythe blade` — how the donor exhibits two ends of the crescent body
- `shell fragment` — how the donor exhibits two ends of the crescent body
- `spiral shell` — the spiral shell exhibits an asymmetrically curved shape with inward-curving spirals
- `humpback whale fin` — the humpback whale fin has an asymmetrically curved shape with a distinct inward curve
- `butterfly wing vein` — the butterfly wing vein exhibits an asymmetrically curved pattern with inward-curving branches
- `spoon handle` — the spoon handle is connected to the main body of the spoon
- `eyelash` — the eyelash is connected to the main body of the eye
- `antenna` — the antenna is connected to the main body of an insect
- `glass surface` — how the donor exhibits smooth and continuous
- `ice surface` — how the donor exhibits smooth and continuous
- `ocean surface` — how the donor exhibits smooth and continuous

**getty_aat**（18 条）
- `spiral shell` — how the donor exhibits tapered pointed ends curving inward
- `arrowhead shape` — how the donor exhibits tapered pointed ends curving inward
- `clam shell` — how the donor exhibits tapered pointed ends curving inward
- `shell shape` — the curved, inward-tapering form of a shell resembles the crescent silhouette
- `moon phase` — the crescent moon shape directly embodies the crescent silhouette
- `wave crest` — the curved, tapered shape of a wave crest mirrors the crescent silhouette
- `shell valve` — shell valve exhibits two ends of the crescent body through its naturally curved and tapered form
- `fishbone pattern` — fishbone pattern exhibits two ends of the crescent body through its segmented, tapering structure
- `spiral phyllotaxis` — spiral phyllotaxis exhibits two ends of the crescent body through its spiral arrangement of leaves or seeds
- `shell shape` — shell shape exhibits asymmetrically curved through its natural, inward-curving form
- `wave pattern` — wave pattern exhibits asymmetrically curved through its undulating, uneven curvature
- `bark texture` — bark texture exhibits asymmetrically curved through its irregular, uneven surface contours
- `spiral stair` — the spiral stair is connected to the main body through its central support structure
- `winged motif` — the winged motif is connected to the main body through its attachment to the central figure
- `branching vein` — the branching vein is connected to the main body through its origin from the central stem
- `glass surface` — glass surface exhibits smooth and continuous through its molecular structure and lack of irregularities
- `ice formation` — ice formation exhibits smooth and continuous through its crystalline structure and uniform growth patterns
- `wax coating` — wax coating exhibits smooth and continuous through its viscous and even application properties

**asknature**（18 条）
- `spider web` — how the donor exhibits tapered pointed ends curving inward
- `beaver tail` — how the donor exhibits tapered pointed ends curving inward
- `arrowhead` — how the donor exhibits tapered pointed ends curving inward
- `spiral shell` — the spiral shell exhibits a crescent-like curvature in its growth pattern
- `mantis shrimp claw` — the mantis shrimp claw has a crescent-shaped tip for striking prey
- `butterfly wing vein` — the butterfly wing vein forms a crescent shape along the wing's edge
- `spider web` — spider web exhibits two ends of the crescent body through its radial symmetry and tapering structure
- `mussel byssus` — mussel byssus exhibits two ends of the crescent body through its fibrous, tapered threads
- `beaver tail` — beaver tail exhibits two ends of the crescent body through its curved, tapered shape
- `spiral shell` — the spiral shell exhibits an asymmetrically curved shape with two inward-curving tips
- `humpback whale flipper` — the humpback whale flipper has an asymmetrically curved structure with a tapered inward curve
- `butterfly wing vein` — the butterfly wing vein exhibits an asymmetrically curved pattern with inward-curving branches
- `spider web` — spider web has a central hub connected to multiple radial threads
- `antennae` — antennae are connected to the main body of an insect
- `leaf veins` — leaf veins are connected to the main body of the leaf
- `whale skin` — whale skin exhibits a smooth and continuous surface due to its layered structure and natural curvature
- `snake scales` — snake scales form a smooth and continuous surface through their overlapping arrangement and seamless alignment
- `butterfly wing` — butterfly wings have a smooth and continuous surface created by the alignment of microscopic scales

## Pretzel（pretzel）

部件：twist knot, loop segment, rope body

### 部件：twist knot（64.67s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：twist knot
- source_noun：pretzel

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | overlapping twist where the rope crosses | central overlapping crossover | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_02 | selected_part_function | distinctive braid structure | central overlapping crossover | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_03 | attachment_logic | center of the pretzel where strands cross | central overlapping crossover | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_04 | orientation | symmetrical crossing pattern | central overlapping crossover | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_05 | articulation | interlocking strands | central overlapping crossover | which concrete cross-domain entities exhibit this same relational property? | 0.9 |
| attr_06 | interface | visible crossover point | central overlapping crossover | which concrete cross-domain entities exhibit this same relational property? | 0.9 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（18 条）
- `DNA double helix` — how the donor exhibits overlapping twist where the rope crosses
- `twisted ribbon` — how the donor exhibits overlapping twist where the rope crosses
- `knotweed stem` — how the donor exhibits overlapping twist where the rope crosses
- `braided river` — braided river exhibits a distinctive braid structure through its branching and intertwining channels
- `braided hair` — braided hair exhibits a distinctive braid structure through its interwoven strands
- `braided rope` — braided rope exhibits a distinctive braid structure through its layered and intertwined fibers
- `DNA double helix` — how the donor exhibits center of the pretzel where strands cross
- `knot in rope` — how the donor exhibits center of the pretzel where strands cross
- `starfish arm` — how the donor exhibits center of the pretzel where strands cross
- `braided rope` — the braided rope exhibits a symmetrical crossing pattern through its interwoven strands
- `knotted chain` — the knotted chain displays a symmetrical crossing pattern in its linked structure
- `woven basket` — the woven basket features a symmetrical crossing pattern in its interlaced fibers
- `braided rope` — braided rope exhibits interlocking strands through the weaving of multiple fibers
- `knotted chain` — knotted chain exhibits interlocking strands through the overlapping of individual links
- `woven basket` — woven basket exhibits interlocking strands through the interlacing of plant fibers
- `DNA double helix` — the DNA double helix exhibits visible crossover points where strands intertwine
- `knotted rope` — a knotted rope has visible crossover points where strands cross over each other
- `braided cable` — a braided cable exhibits visible crossover points where individual strands interweave

**getty_aat**（18 条）
- `twisted fiber bundle` — how the donor exhibits overlapping twist where the rope crosses
- `braided strand` — how the donor exhibits overlapping twist where the rope crosses
- `coiled wire` — how the donor exhibits overlapping twist where the rope crosses
- `twisted fiber bundle` — the twisted fiber bundle exhibits a distinctive braid structure through overlapping crossovers similar to the source attribute
- `braided rope` — braided rope demonstrates a distinctive braid structure through central overlapping crossovers
- `helical strand` — helical strand forms a distinctive braid structure through a central overlapping crossover pattern
- `knotted fiber junction` — how the donor exhibits center of the pretzel where strands cross
- `braided strand intersection` — how the donor exhibits center of the pretzel where strands cross
- `twisted rope node` — how the donor exhibits center of the pretzel where strands cross
- `twisted rope` — the twisted rope exhibits a symmetrical crossing pattern through its interwoven strands
- `braided fiber` — the braided fiber forms a symmetrical crossing pattern through its interlaced structure
- `knotted cord` — the knotted cord demonstrates a symmetrical crossing pattern through its tightly interlocked loops
- `braided fibers` — braided fibers exhibit interlocking strands through overlapping twisted layers
- `woven mesh` — woven mesh exhibits interlocking strands through crossed and interlaced threads
- `knotted rope` — knotted rope exhibits interlocking strands through overlapping and twisted segments
- `braided cord` — braided cord exhibits visible crossover point through the interlacing of strands
- `knotted rope` — knotted rope exhibits visible crossover point through the interweaving of rope segments
- `woven basket` — woven basket exhibits visible crossover point through the crossing of woven fibers

**asknature**（18 条）
- `spiral shell` — the spiral shell exhibits overlapping twist where the rope crosses
- `dna double helix` — the dna double helix exhibits overlapping twist where the rope crosses
- `twisted vine` — the twisted vine exhibits overlapping twist where the rope crosses
- `spider web` — spider web exhibits a distinctive braid structure through its interwoven silk threads
- `moss carpet` — moss carpet forms a distinctive braid structure through layered, interwoven growth patterns
- `fern frond` — fern frond displays a distinctive braid structure through its layered, overlapping leaflets
- `spider web junction` — how the donor exhibits center of the pretzel where strands cross
- `flower petal node` — how the donor exhibits center of the pretzel where strands cross
- `bee hive cell` — how the donor exhibits center of the pretzel where strands cross
- `spider web` — spider web exhibits symmetrical crossing pattern through its radial and spiral threads
- `bee hive comb` — bee hive comb exhibits symmetrical crossing pattern through its hexagonal grid structure
- `leaf venation` — leaf venation exhibits symmetrical crossing pattern through its branching network
- `bee hive comb` — bee hive comb exhibits interlocking strands through the hexagonal cell structure
- `seashell spiral` — seashell spiral exhibits interlocking strands through its layered, coiled structure
- `spider web` — spider web exhibits interlocking strands through its network of silk threads
- `spider web junction` — spider web junction exhibits a visible crossover point where threads intersect
- `vein branching point` — vein branching point exhibits a visible crossover point where blood vessels intersect
- `leaf node junction` — leaf node junction exhibits a visible crossover point where branches meet

### 部件：loop segment（65.64s）

#### 1. KG 属性规划（attribute_plan）

- source_anchor：loop segment
- source_noun：pretzel

| attribute_id | dimension | value | evidence | transfer_question | confidence |
|---|---|---|---|---|---|
| attr_01 | selected_part_shape | thick rounded rope arms forming loops | two symmetric thick loops | which concrete cross-domain entities exhibit this same relational property? | 0.92 |
| attr_02 | selected_part_function | defines the pretzel outline | two symmetric thick loops | which concrete cross-domain entities exhibit this same relational property? | 0.92 |
| attr_03 | attachment_logic | two symmetric loops flanking the knot | two symmetric thick loops | which concrete cross-domain entities exhibit this same relational property? | 0.92 |
| attr_04 | orientation | horizontal loops | two symmetric thick loops | which concrete cross-domain entities exhibit this same relational property? | 0.92 |
| attr_05 | articulation | continuous loop segments | two symmetric thick loops | which concrete cross-domain entities exhibit this same relational property? | 0.92 |
| attr_06 | interface | smooth transition between loops and knot | two symmetric thick loops | which concrete cross-domain entities exhibit this same relational property? | 0.92 |

#### 2. 发散的相关词（KG 查询词）

**wikidata**（18 条）
- `braided rope loops` — how the donor exhibits thick rounded rope arms forming loops
- `knotted chain links` — how the donor exhibits thick rounded rope arms forming loops
- `twisted cable coils` — how the donor exhibits thick rounded rope arms forming loops
- `seashell spiral` — the spiral shape of a seashell defines its outline through a natural growth pattern
- `fern frond` — the fern frond exhibits a defined outline through its branching, spiral-like structure
- `spiral galaxy` — the spiral galaxy's outline is defined by its rotational structure and arm patterns
- `double helix` — the double helix structure exhibits two symmetric loops flanking the central axis
- `DNA strand` — the DNA strand forms two symmetric loops flanking the central helical structure
- `twisted ribbon` — the twisted ribbon exhibits two symmetric loops flanking the central twisted core
- `spiral staircase` — the balustrade of a spiral staircase forms horizontal loops along its curvature
- `chain link fence` — the horizontal links of a chain link fence form repeating loop patterns
- `wave pattern` — the crest and trough of a wave form horizontal loop-like structures
- `spiral staircase` — spiral staircase exhibits continuous loop segments through its helical structure
- `dna double helix` — dna double helix exhibits continuous loop segments through its twisted ladder structure
- `chain link fence` — chain link fence exhibits continuous loop segments through its interlocking metal loops
- `seashell spiral` — the spiral structure of a seashell exhibits a smooth transition between loops and knot-like formations
- `fern frond` — the fern frond displays a smooth transition between loops and knot-like structures in its branching pattern
- `river meander` — the river meander exhibits a smooth transition between loops and knot-like bends in its flow

**getty_aat**（18 条）
- `twisted rope` — the twisted rope forms thick rounded arms that create looped structures
- `braided cord` — the braided cord creates thick, rounded arms that form looped shapes
- `knotted chain` — the knotted chain exhibits thick, rounded arms that form looped structures
- `twisted wire` — the twisted wire forms a symmetrical loop structure similar to the pretzel outline
- `braided fiber` — the braided fiber creates a looped, symmetrical pattern akin to the pretzel outline
- `spiral shell` — the spiral shell exhibits a natural looped structure resembling the pretzel outline
- `double helix` — the double helix structure of DNA exhibits two symmetric loops flanking the central axis
- `twisted ribbon` — the twisted ribbon structure exhibits two symmetric loops flanking the central twist
- `coiled spring` — the coiled spring exhibits two symmetric loops flanking the central coil
- `wave pattern` — wave pattern exhibits horizontal loops through repetitive undulating forms
- `riverside meander` — riverside meander exhibits horizontal loops through natural winding paths
- `spiral shell` — spiral shell exhibits horizontal loops through layered concentric formations
- `spiral curls` — spiral curls exhibit continuous loop segments through their helical formation
- `braided fibers` — braided fibers form continuous loop segments through interwoven strands
- `coiled springs` — coiled springs exhibit continuous loop segments through their helical compression structure
- `woven basket weave` — the interlacing of fibers creates a smooth transition between loops and knot-like intersections
- `seashell spiral` — the natural spiral of a seashell exhibits a smooth transition between loops and knot-like formations
- `braided rope` — the braiding process creates a smooth transition between loops and knot-like intersections

**asknature**（18 条）
- `spider web silks` — spider web silks exhibit thick rounded rope arms forming loops through their fibrous structure
- `mussel byssus threads` — mussel byssus threads form thick rounded rope arms that loop around surfaces for attachment
- `fern frond veins` — fern frond veins create thick rounded rope arms that form looping structures for water transport
- `spiral shell` — the spiral shell exhibits a defined outline through its coiled structure
- `fern frond` — the fern frond defines its outline through its branching, loop-like structure
- `honeycomb` — the honeycomb defines its outline through its repeating, looped hexagonal cells
- `spider web anchor` — the spider web anchor exhibits two symmetric loops flanking the knot
- `mussel foot` — the mussel foot exhibits two symmetric loops flanking the knot
- `barnacle holdfast` — the barnacle holdfast exhibits two symmetric loops flanking the knot
- `spider web` — spider web exhibits horizontal loops in its radial pattern
- `leaf veins` — leaf veins form horizontal loops in their network structure
- `mussel byssus` — mussel byssus has horizontal loops in its fibrous thread arrangement
- `spider web` — spider web exhibits continuous loop segments through its interconnected silk threads
- `seashell spiral` — seashell spiral exhibits continuous loop segments through its logarithmic growth pattern
- `fern frond` — fern frond exhibits continuous loop segments through its repeated, curling leaflets
- `spider web silk` — spider web silk exhibits a smooth transition between loops and knot-like structures in its fibrous network
- `mussel byssus thread` — mussel byssus thread features a smooth transition between loops and knot-like structures for secure attachment
- `lotus leaf veins` — lotus leaf veins demonstrate a smooth transition between loops and knot-like branching patterns
