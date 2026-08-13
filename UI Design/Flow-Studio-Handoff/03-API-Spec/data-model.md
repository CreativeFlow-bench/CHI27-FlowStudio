# Data model

## Project

`id`, `name`, `ownerId`, `locale`, `activeVersionId`, `createdAt`, `updatedAt`, `status`

## Asset

`id`, `projectId`, `filename`, `format`, `size`, `storageUrl`, `previewUrl`, `processingStatus`, `metadata`

## Version

`id`, `projectId`, `parentVersionId`, `number`, `name`, `assetId`, `transform`, `camera`, `createdFromDirectionId`, `createdAt`

## OperationEvent

`id`, `projectId`, `versionId`, `tool`, `target`, `modelSpaceData`, `strength`, `camera`, `note`, `createdAt`

## Intent

`id`, `projectId`, `versionId`, `status`, `primary`, `text`, `confidence`, `evidenceEventIds`, `referencedVersionIds`, `createdAt`, `confirmedAt`

## CombinedIntent

`id`, `projectId`, `sourceIntentIds`, `text`, `conflicts`, `updatedAt`

## Direction

`id`, `projectId`, `combinedIntentId`, `aestheticTerms`, `structuralTerms`, `status`, `previewUrl`, `prompt`, `createdAt`

## GenerationJob

`id`, `projectId`, `type`, `status`, `progress`, `input`, `output`, `error`, `createdAt`, `completedAt`

## Stable enums

- Intent status: `INFERRING`, `STATED`, `CONFIRMED`, `DISMISSED`
- Job status: `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`
- Tool: `NAVIGATE`, `SELECT`, `BRUSH`, `SKETCH`, `PULL`, `SMOOTH`, `ADD`
- Locale: `en`, `zh-CN`

