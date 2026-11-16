import type { components } from './schema';

export type Schemas = components['schemas'];

export type Asset = Schemas['AssetResponse'];
export type AssetPatch = Schemas['AssetPatchRequest'];
export type Observation = Schemas['ObservationResponse'];
export type Defect = Schemas['DefectResponse'];
export type DefectPatch = Schemas['DefectPatchRequest'];
export type Review = Schemas['ReviewResponse'];
export type ReviewCreate = Schemas['ReviewCreateRequest'];
export type Job = Schemas['JobResponse'];
export type JobFrame = Schemas['JobFrameResponse'];
export type JobCreate = Schemas['JobCreateRequest'];
export type Upload = Schemas['UploadResponse'];
export type UploadCreate = Schemas['UploadCreateResponse'];
export type Route = Schemas['RouteResponse'];
export type RouteCreate = Schemas['RouteCreateRequest'];
export type User = Schemas['UserResponse'];
export type TokenResponse = Schemas['TokenResponse'];
export type AnalyticsOverview = Schemas['AnalyticsOverview'];
export type DefectsAnalytics = Schemas['DefectsAnalytics'];
export type CoverageResponse = Schemas['CoverageResponse'];
export type ConditionHistory = Schemas['ConditionHistoryResponse'];
export type MLHealth = Schemas['MLHealth'];
export type MLModelInfo = Schemas['MLModelInfo'];
export type ErrorResponse = Schemas['ErrorResponse'];
export type AssetMapFeature = Schemas['Feature_AssetMapProperties_'];
export type DefectMapFeature = Schemas['Feature_DefectMapProperties_'];
export type ObservationMapFeature = Schemas['Feature_ObservationMapProperties_'];
export type RouteMapFeature = Schemas['Feature_RouteMapProperties_'];
export type AssetMapCollection = Schemas['FeatureCollection_AssetMapProperties_'];
export type DefectMapCollection = Schemas['FeatureCollection_DefectMapProperties_'];
export type ObservationMapCollection = Schemas['FeatureCollection_ObservationMapProperties_'];
export type RouteMapCollection = Schemas['FeatureCollection_RouteMapProperties_'];

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export type AssetPage = Schemas['PageResponse_AssetResponse_'];
export type ObservationPage = Schemas['PageResponse_ObservationResponse_'];
export type DefectPage = Schemas['PageResponse_DefectResponse_'];
export type JobPage = Schemas['PageResponse_JobResponse_'];
export type ReviewPage = Schemas['PageResponse_ReviewResponse_'];
export type RoutePage = Schemas['PageResponse_RouteResponse_'];
export type UploadPage = Schemas['PageResponse_UploadResponse_'];
export type HistoryPage = Schemas['PageResponse_ConditionHistoryResponse_'];
export type FramePage = Schemas['PageResponse_JobFrameResponse_'];