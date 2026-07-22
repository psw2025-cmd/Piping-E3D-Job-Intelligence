# Official Oracle Requisition Verification

Two-record, read-only calls to fixed official career hosts. No response bodies are committed.

## McDermott

- HTTP status: `200`
- Response bytes: `6903`
- Top-level keys: `count, hasMore, items, limit, links, offset`
- Wrapper items: `1`
- hasMore: `False`
- First wrapper keys: `BotQRShortCode, CandidateNumber, CorrectedKeyword, ExecuteSpellCheckFlag, Facets, HotJobFlag, JobFamilyId, Keyword, LastSelectedFacet, Latitude, Limit, Location, LocationId, Longitude, Offset, OrganizationId, PostingEndDate, PostingStartDate, Radius, RadiusUnit, RequisitionId, SearchId, SelectedCategoriesFacet, SelectedFlexFieldsFacets, SelectedLocationsFacet, SelectedOrganizationsFacet, SelectedPostingDatesFacet, SelectedTitlesFacet, SelectedWorkLocationsFacet, SelectedWorkplaceTypesFacet, SiteNumber, SortBy, SuggestedKeyword, TotalJobsCount, UseExactKeywordFlag, UserTargetFacetInputTerm, UserTargetFacetName, WorkLocationCountryCode, WorkLocationZipCode, WorkplaceType, categoriesFacet, flexFieldsFacet, locationsFacet, organizationsFacet, postingDatesFacet, requisitionList, titlesFacet, workLocationsFacet, workplaceTypesFacet`
- Requisition rows in first wrapper: `2`
- First requisition keys: `BeFirstToApplyFlag, BusinessUnit, BusinessUnitId, ContractType, Department, Distance, DomesticTravelRequired, ExternalQualificationsStr, ExternalResponsibilitiesStr, GeographyId, HotJobFlag, Id, InternationalTravelRequired, JobFamily, JobFunction, JobSchedule, JobShift, JobType, Language, LegalEmployer, LegalEmployerId, ManagerLevel, MediaThumbURL, Organization, OrganizationId, PostedDate, PostingEndDate, PrimaryLocation, PrimaryLocationCountry, Relevancy, ShortDescriptionStr, StudyLevel, Title, TrendingFlag, WorkDays, WorkDurationMonths, WorkDurationYears, WorkHours, WorkerType, WorkplaceType, WorkplaceTypeCode`
- Public sample: `{"PostedDate": "2026-07-22", "PrimaryLocation": "Chennai, Tamil Nadu, India", "Title": "Senior IT Pillar Specialist"}`
- Connector-compatible: **YES**

## Wood

- HTTP status: `200`
- Response bytes: `7092`
- Top-level keys: `count, hasMore, items, limit, links, offset`
- Wrapper items: `1`
- hasMore: `False`
- First wrapper keys: `BotQRShortCode, CandidateNumber, CorrectedKeyword, ExecuteSpellCheckFlag, Facets, HotJobFlag, JobFamilyId, Keyword, LastSelectedFacet, Latitude, Limit, Location, LocationId, Longitude, Offset, OrganizationId, PostingEndDate, PostingStartDate, Radius, RadiusUnit, RequisitionId, SearchId, SelectedCategoriesFacet, SelectedFlexFieldsFacets, SelectedLocationsFacet, SelectedOrganizationsFacet, SelectedPostingDatesFacet, SelectedTitlesFacet, SelectedWorkLocationsFacet, SelectedWorkplaceTypesFacet, SiteNumber, SortBy, SuggestedKeyword, TotalJobsCount, UseExactKeywordFlag, UserTargetFacetInputTerm, UserTargetFacetName, WorkLocationCountryCode, WorkLocationZipCode, WorkplaceType, categoriesFacet, flexFieldsFacet, locationsFacet, organizationsFacet, postingDatesFacet, requisitionList, titlesFacet, workLocationsFacet, workplaceTypesFacet`
- Requisition rows in first wrapper: `2`
- First requisition keys: `BeFirstToApplyFlag, BusinessUnit, BusinessUnitId, ContractType, Department, Distance, DomesticTravelRequired, ExternalQualificationsStr, ExternalResponsibilitiesStr, GeographyId, HotJobFlag, Id, InternationalTravelRequired, JobFamily, JobFunction, JobSchedule, JobShift, JobType, Language, LegalEmployer, LegalEmployerId, ManagerLevel, MediaThumbURL, Organization, OrganizationId, PostedDate, PostingEndDate, PrimaryLocation, PrimaryLocationCountry, Relevancy, ShortDescriptionStr, StudyLevel, Title, TrendingFlag, WorkDays, WorkDurationMonths, WorkDurationYears, WorkHours, WorkerType, WorkplaceType, WorkplaceTypeCode`
- Public sample: `{"PostedDate": "2026-07-22", "PrimaryLocation": "Offshore, United Kingdom", "Title": "Mechanical Technician - CNOOC Scott"}`
- Connector-compatible: **YES**
