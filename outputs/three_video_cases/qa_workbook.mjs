import { SpreadsheetFile } from "@oai/artifact-tool";

const path = "/Users/primav/Documents/博一/CHI27-FlowStudio/outputs/three_video_cases/FlowStudio_三视频_behavior_state案例库.xlsx";
const wb = await SpreadsheetFile.importXlsx(path);
for (const range of ["案例库!A1:L6", "案例库!A20:L22", "后续标注!A1:H6", "说明与概览!A3:C19"]) {
  console.log(`RANGE ${range}`);
  console.log(wb.inspect({kind:"table",range,include:"values,formulas",tableMaxRows:30,tableMaxCols:15}).ndjson);
}
console.log("ERROR_SCAN");
console.log(wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",options:{useRegex:true,maxResults:100},summary:"formula errors"}).ndjson);
