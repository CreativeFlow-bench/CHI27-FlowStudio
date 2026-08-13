import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outDir = "/Users/primav/Documents/博一/CHI27-FlowStudio/outputs/three_video_cases";
const nomadPath = "/Users/primav/.codex/attachments/d16e6f43-5001-46f0-adbf-4a56efa622ad/pasted-text.txt";
const newCasesPath = `${outDir}/new_cases.json`;

const maya = [
  ["maya_low_poly_rocks_01","00:13","00:56","coarse forming",["Select the Platonic Solid primitive icon on the Poly Modeling shelf","Open the Attribute Editor on the right panel","Change 'Primitive' to 'Tetrahedron' under the polyPlatonicHistory node","Keep 'Subdivisions' at 1.0"],"A clean 4-sided tetrahedron is generated in the viewport to serve as the initial base block of the rock."],
  ["maya_low_poly_rocks_02","00:57","02:22","coarse forming",["Switch to Vertex Selection Mode (selection method: unknown)","Select a vertex on the tetrahedron","Activate Soft Selection, causing a colored gradient falloff to overlay on the mesh vertices","Drag and rotate vertex regions using the viewport move/rotate gizmos","Deactivate Soft Selection"],"The symmetrical tetrahedron is warped into an irregular, asymmetrical, blocky rock shape."],
  ["maya_low_poly_rocks_03","02:58","03:32","workflow transition",["Select the warped mesh in Object Mode","Click 'Mesh' -> 'Retopologize' from the top menu and open its options dialog","Set 'Target face count' to 5000 and 'Face uniformity' to 1.0","Click the 'Retopologize' button to execute"],"The irregular mesh is reconstructed into a dense, evenly distributed quad-based grid to prepare for detail sculpting."],
  ["maya_low_poly_rocks_04","03:33","05:14","local refinement",["Select the Sculpting tab on the shelf and click the first sculpting brush (brush type: unknown)","Adjust brush size and strength (interaction shortcuts: unknown)","Apply strokes across the surface to build up irregular organic bumps","Hold down a modifier key (unknown) to smooth out sharp corners"],"The rock surface receives uneven organic lump details while harsh edges are softened."],
  ["maya_low_poly_rocks_05","05:55","06:12","local refinement",["Select the sculpted mesh in Object Mode","Click 'Mesh' -> 'Triangulate' from the top menu","Click 'Mesh Display' -> 'Harden Edge' to force flat, hard-edge shading"],"The high-density sculpted quad mesh is converted into triangles and hard-shaded to show sharp, faceted planes."],
  ["maya_low_poly_rocks_06","06:13","06:55","coarse forming",["Delete history (interaction method: unknown)","Click 'Mesh' -> 'Reduce' from the top menu to open the reduce options","Drag the 'Percentage' slider dynamically up to 100%, then slide it back to reduce face count"],"The mesh is decimated into a low-poly structure, creating clean, simplified facets."],
  ["maya_low_poly_rocks_07","07:01","07:31","evaluation",["Open the right-click marking menu on the rock mesh","Select 'Assign Existing Material' -> 'lambert2' (or unknown material name)","Toggle 'Wireframe on Shaded' in the viewport header (selection method: unknown)","Orbit the camera around the rock model to review the faceted shading"],"The model is shaded with a brown Lambert material to evaluate flat-shading silhouette consistency."]
].map(([case_id,start,end,state,signals,result]) => ({case_id,start,end,state,signals,result,source:"https://www.youtube.com/watch?v=ymoIXvR0Aek"}));

const blender = [
  ["blender_bros_scifi_sensor_01","00:05","00:18","coarse forming",["Select the default cube mesh","Switch viewport view to Right Orthographic","Invoke a deformation tool (tool name: unknown)","Select and drag control points in the lattice viewport grid to warp the top profile of the mesh"],"The top face of the rectangular block is bent into a smooth curve using a control lattice."],
  ["blender_bros_scifi_sensor_02","00:35","00:54","exploration",["Activate an unknown hard-surface cutting tool","Draw a polygonal cutting template across the top corner of the mesh","Perform multiple undo operations (indicated by 'Ctrl + Z x12' on-screen text)","Re-draw the cutting template at a different angle to slice the corner"],"The user tests different angled corner cuts to choose the optimal front profile for the model."],
  ["blender_bros_scifi_sensor_03","01:25","02:11","local refinement",["Create and place a cylinder primitive intersecting the side of the mesh","Execute an unknown boolean subtraction operation to carve a circular recess","Select and inset the interior circular face (tool/method: unknown) to add concentric ring details"],"A clean concentric circular port detail is modeled into the side face."],
  ["blender_bros_scifi_sensor_04","05:01","05:13","coarse forming",["Select a curve line path at the bottom of the mesh","Open a radial popup menu (menu name: unknown)","Trigger an unknown conversion function to change the path into a solid tube (indicated by 'To_Curve' on-screen text)"],"A curved three-dimensional structural pipe is generated on the underside of the model."],
  ["blender_bros_scifi_sensor_05","07:22","07:34","local refinement",["Activate an unknown hard-surface cutting tool","Draw several parallel vertical slicing templates across the back curved face of the body","Apply the cuts to carve slots (indicated by 'Csharp (apply)' on-screen text)"],"A series of clean parallel vent slots are modeled on the curved rear face."],
  ["blender_bros_scifi_sensor_06","08:18","08:42","local refinement",["Align multiple circular cutting shapes over the flat front face of the model","Apply an unknown boolean subtraction tool to punch holes in the surface"],"The front face of the model receives three circular lens apertures of different sizes."],
  ["blender_bros_scifi_sensor_07","09:55","10:26","evaluation",["Switch viewport shading to a reflective metallic matcap","Trigger an unknown normal editing tool (indicated by 'Weighted Normal' on-screen text)","Perform a continuous 360-degree camera orbit around the model to inspect surface reflections"],"The model's shading quality and edge highlight reflections are reviewed for artifacts."]
].map(([case_id,start,end,state,signals,result]) => ({case_id,start,end,state,signals,result,source:"https://www.youtube.com/watch?v=UMO9r4W9Xm0"}));

const timeValue = (s) => {
  const [m, sec] = s.split(":").map(Number);
  return (m * 60 + sec) / 86400;
};
const timeSeconds = (s) => {
  const [m, sec] = s.split(":").map(Number);
  return m * 60 + sec;
};
const metadata = (c) => {
  if (c.case_id.startsWith("nomad_char_")) return ["Nomad Character Sculpt", "Nomad Sculpt"];
  if (c.case_id.startsWith("nomad_")) return ["Nomad Sculpt Low Poly Sword", "Nomad Sculpt"];
  if (c.case_id.startsWith("maya_")) return ["Maya Low Poly Rocks", "Maya"];
  if (c.case_id.startsWith("blender_bros_")) return ["Blender Bros Sci-Fi Sensor", "Blender"];
  if (c.case_id.startsWith("stylized_character_sculpt_")) return ["Stylized Character Sculpt", "Nomad Sculpt"];
  if (c.case_id.startsWith("chibi_character_modeling_")) return ["Chibi Character Modeling", "Blender"];
  if (c.case_id.startsWith("snowman_modeling_")) return ["Snowman Modeling", "Blender"];
  return ["Stylized Male Character Sculpt", "ZBrush"];
};

const nomad = JSON.parse(await fs.readFile(nomadPath, "utf8"));
const newCases = JSON.parse(await fs.readFile(newCasesPath, "utf8"));
const cases = [...nomad, ...maya, ...blender, ...newCases];
if (cases.length !== 58) throw new Error(`Expected 58 cases, got ${cases.length}`);
if (new Set(cases.map(c => c.case_id)).size !== cases.length) throw new Error("Duplicate case_id detected");

const wb = Workbook.create();
const main = wb.worksheets.add("案例库");
const follow = wb.worksheets.add("后续标注");
const guide = wb.worksheets.add("说明与概览");

const headers = ["case_id","video","software","start","end","duration","state","signals（逐条）","result","source（带时间点）","human_verified","notes"];
const rows = cases.map(c => {
  const [video, software] = metadata(c);
  const sep = c.source.includes("?") ? "&" : "?";
  return [c.case_id,video,software,timeValue(c.start),timeValue(c.end),null,c.state,c.signals.map((x,i)=>`${i+1}. ${x}`).join("\n"),c.result,`${c.source}${sep}t=${timeSeconds(c.start)}s`,"待核验",c.notes || ""];
});

main.getRange("A1:L1").values = [headers];
main.getRange(`A2:L${rows.length+1}`).values = rows;
main.getRange("F2").formulas = [["=E2-D2"]];
main.getRange(`F2:F${rows.length+1}`).fillDown();
main.freezePanes.freezeRows(1);
main.getRange("A1:L1").format = {fill:"#203864",font:{bold:true,color:"#FFFFFF"},verticalAlignment:"center",horizontalAlignment:"center",wrapText:true};
main.getRange(`A2:L${rows.length+1}`).format = {verticalAlignment:"top",wrapText:true};
main.getRange(`D2:F${rows.length+1}`).format.numberFormat = "[m]:ss";
main.getRange(`A1:L${rows.length+1}`).format.borders = {top:{style:"continuous",color:"#D9E2F3"},bottom:{style:"continuous",color:"#D9E2F3"},left:{style:"continuous",color:"#D9E2F3"},right:{style:"continuous",color:"#D9E2F3"}};
main.getRange("A:A").format.columnWidth = 31;
main.getRange("B:B").format.columnWidth = 28;
main.getRange("C:C").format.columnWidth = 14;
main.getRange("D:F").format.columnWidth = 10;
main.getRange("G:G").format.columnWidth = 19;
main.getRange("H:H").format.columnWidth = 62;
main.getRange("I:I").format.columnWidth = 48;
main.getRange("J:J").format.columnWidth = 43;
main.getRange("K:K").format.columnWidth = 14;
main.getRange("L:L").format.columnWidth = 26;
main.getRange(`K2:K${rows.length+1}`).dataValidation = {rule:{type:"list",formula1:'"待核验,是,部分,否"'}};
main.getRange(`G2:G${rows.length+1}`).conditionalFormats.addCustom("=G2=\"exploration\"",{fill:"#FFF2CC"});
main.getRange(`G2:G${rows.length+1}`).conditionalFormats.addCustom("=G2=\"coarse forming\"",{fill:"#DDEBF7"});
main.getRange(`G2:G${rows.length+1}`).conditionalFormats.addCustom("=G2=\"local refinement\"",{fill:"#E2F0D9"});
main.getRange(`G2:G${rows.length+1}`).conditionalFormats.addCustom("=G2=\"evaluation\"",{fill:"#E4DFEC"});
main.getRange(`G2:G${rows.length+1}`).conditionalFormats.addCustom("=G2=\"workflow transition\"",{fill:"#FCE4D6"});
main.getRange(`G2:G${rows.length+1}`).conditionalFormats.addCustom("=G2=\"relationship adjustment\"",{fill:"#DDEBF7",font:{color:"#1F4E78"}});
main.getRange(`G2:G${rows.length+1}`).conditionalFormats.addCustom("=G2=\"repair\"",{fill:"#F4CCCC",font:{color:"#9C0006"}});
main.tables.add(`A1:L${rows.length+1}`, true, "CaseLibraryTable");

const followHeaders = ["case_id","observed_state","normalized_state","creative_stage","divergence_need","CreativeFlow_route","intervention_boundary","evidence_note"];
follow.getRange("A1:H1").values = [followHeaders];
follow.getRange(`A2:H${cases.length+1}`).values = cases.map(c => [c.case_id,c.state,"待定","待定","待定","待定","待定",""]);
follow.freezePanes.freezeRows(1);
follow.getRange("A1:H1").format = {fill:"#4472C4",font:{bold:true,color:"#FFFFFF"},horizontalAlignment:"center",verticalAlignment:"center",wrapText:true};
follow.getRange(`A2:H${cases.length+1}`).format = {verticalAlignment:"top",wrapText:true};
follow.getRange("A:A").format.columnWidth = 31;
follow.getRange("B:C").format.columnWidth = 21;
follow.getRange("D:D").format.columnWidth = 18;
follow.getRange("E:G").format.columnWidth = 22;
follow.getRange("H:H").format.columnWidth = 42;
follow.getRange(`C2:C${cases.length+1}`).dataValidation = {rule:{type:"list",formula1:'"待定,exploration,coarse forming,local refinement,relationship adjustment,evaluation,workflow transition,repair,commitment,other"'}};
follow.getRange(`E2:E${cases.length+1}`).dataValidation = {rule:{type:"list",formula1:'"待定,none,low,medium,high"'}};
follow.tables.add(`A1:H${cases.length+1}`, true, "FollowupLabelsTable");

guide.getRange("A1:F1").merge();
guide.getRange("A1").values = [["FlowStudio · 八视频行为状态案例库"]];
guide.getRange("A1:F1").format = {fill:"#203864",font:{bold:true,color:"#FFFFFF",size:16},horizontalAlignment:"left",verticalAlignment:"center"};
guide.getRange("A3:B7").values = [
  ["用途","一行一个可检索的小案例；先核验行为证据，再补 CreativeFlow 路由标签。"],
  ["案例总数",cases.length],
  ["视频数",8],
  ["最小 JSON 字段","case_id / start / end / state / signals / result / source"],
  ["当前建议","不要再把 episode 拆得更细；只有结果状态发生可解释变化时才另起案例。"]
];
guide.getRange("A3:A7").format = {fill:"#D9E2F3",font:{bold:true,color:"#203864"},verticalAlignment:"top"};
guide.getRange("A3:B7").format.wrapText = true;
guide.getRange("A9:C9").values = [["video","case_count","主要覆盖"]];
guide.getRange("A9:C9").format = {fill:"#4472C4",font:{bold:true,color:"#FFFFFF"},horizontalAlignment:"center"};
guide.getRange("A10:C17").values = [
  ["Nomad Sculpt Low Poly Sword",null,"coarse forming / workflow transition / local refinement / evaluation"],
  ["Maya Low Poly Rocks",null,"coarse forming / workflow transition / local refinement / evaluation"],
  ["Blender Bros Sci-Fi Sensor",null,"exploration / coarse forming / local refinement / evaluation"],
  ["Stylized Character Sculpt",null,"coarse forming / repair / local refinement / relationship adjustment / workflow transition"],
  ["Chibi Character Modeling",null,"coarse forming / local refinement / relationship adjustment / repair"],
  ["Stylized Male Character Sculpt",null,"workflow transition / coarse forming / relationship adjustment / local refinement"],
  ["Snowman Modeling",null,"coarse forming / local refinement / workflow transition / relationship adjustment / evaluation"],
  ["Nomad Character Sculpt",null,"workflow transition / coarse forming / local refinement / evaluation / repair"]
];
guide.getRange("B10").formulas = [["=COUNTIF('案例库'!$B$2:$B$59,A10)"]];
guide.getRange("B10:B17").fillDown();
guide.getRange("A19:B19").values = [["state","count"]];
guide.getRange("A19:B19").format = {fill:"#4472C4",font:{bold:true,color:"#FFFFFF"},horizontalAlignment:"center"};
const states = ["exploration","coarse forming","local refinement","relationship adjustment","workflow transition","repair","evaluation"];
guide.getRange("A20:A26").values = states.map(s=>[s]);
guide.getRange("B20").formulas = [["=COUNTIF('案例库'!$G$2:$G$59,A20)"]];
guide.getRange("B20:B26").fillDown();
guide.getRange("A:A").format.columnWidth = 34;
guide.getRange("B:B").format.columnWidth = 24;
guide.getRange("C:C").format.columnWidth = 64;
guide.getRange("1:1").format.rowHeight = 30;
guide.freezePanes.freezeRows(1);

for (const sheet of [main, follow, guide]) {
  const used = sheet.getUsedRange();
  if (used) used.format.font = {name:"Aptos",size:10};
}
main.getRange("A1:L1").format.font = {name:"Aptos",size:10,bold:true,color:"#FFFFFF"};
follow.getRange("A1:H1").format.font = {name:"Aptos",size:10,bold:true,color:"#FFFFFF"};
guide.getRange("A1").format.font = {name:"Aptos Display",size:16,bold:true,color:"#FFFFFF"};

for (const sheetName of ["案例库","后续标注","说明与概览"]) {
  const preview = await wb.render({sheetName,autoCrop:"all",scale:1,format:"png"});
  await fs.writeFile(`${outDir}/${sheetName}.png`,new Uint8Array(await preview.arrayBuffer()));
}
const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(`${outDir}/FlowStudio_八视频_behavior_state案例库.xlsx`);
console.log(JSON.stringify({cases:cases.length, output:`${outDir}/FlowStudio_八视频_behavior_state案例库.xlsx`}));
