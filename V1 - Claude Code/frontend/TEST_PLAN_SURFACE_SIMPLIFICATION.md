# Surface Type Simplification - Test Plan

## Overview

This document describes the programmatic test suite for verifying the surface type simplification implementation. The tests ensure that the conversion from 5 detailed surface categories to 3 simplified categories works correctly across all layers of the application.

## Test Structure

The test suite consists of three main test files:

1. **`src/lib/__tests__/surfaceMix.test.ts`** - Core mapping and aggregation functions
2. **`src/stores/__tests__/surfaceStore.test.ts`** - Store-level aggregation and data flow
3. **`src/lib/__tests__/surfaceEnrichment.test.ts`** - Enrichment integration and feature creation

## Running the Tests

### Run all tests:
```bash
npm test
```

### Run specific test file:
```bash
npm test surfaceMix.test.ts
npm test surfaceStore.test.ts
npm test surfaceEnrichment.test.ts
```

### Run in watch mode:
```bash
npm run test:watch
```

### Run with coverage:
```bash
npm test -- --coverage
```

## Test Coverage

### 1. Core Mapping Functions (`surfaceMix.test.ts`)

#### `mapSurfaceTypeToSimplified`
- ✅ Maps `pavement` → `paved`
- ✅ Maps `gravel` → `unpaved`
- ✅ Maps `dirt` → `unpaved`
- ✅ Maps `singletrack` → `unpaved`
- ✅ Maps `unknown` → `unknown`
- ✅ Handles all surface types systematically

#### `getSimplifiedSurfaceMix`
- ✅ Aggregates `pavement` into `paved`
- ✅ Aggregates `gravel + dirt + singletrack` into `unpaved`
- ✅ Preserves `unknown` as `unknown`
- ✅ Correctly combines mixed surfaces
- ✅ Normalizes percentages to sum to 100
- ✅ Handles edge cases (empty, all zero, partial data)
- ✅ Maintains percentage accuracy for complex breakdowns

#### `getDetailedSurfaceMix`
- ✅ Preserves all 5 surface categories
- ✅ Normalizes detailed breakdown to sum to 100
- ✅ Handles empty breakdowns

#### Data Flow Integration
- ✅ Converts detailed → simplified → detailed correctly
- ✅ Handles real-world route breakdowns
- ✅ Handles MTB routes with mixed unpaved surfaces

#### Edge Cases
- ✅ Breakdowns summing to > 100
- ✅ Breakdowns summing to < 100
- ✅ Very small percentages

### 2. Store-Level Tests (`surfaceStore.test.ts`)

#### `getAggregatedBreakdown`
- ✅ Aggregates segments into detailed breakdown
- ✅ Handles all paved segments
- ✅ Aggregates unpaved segments correctly
- ✅ Handles unknown segments
- ✅ Returns all unknown when no segments

#### Simplified Breakdown Integration
- ✅ Converts aggregated breakdown to simplified correctly
- ✅ Handles mixed routes with all surface types
- ✅ Correctly aggregates long routes with many segments

#### Edge Cases
- ✅ Single segment routes
- ✅ Routes with only unknown segments
- ✅ Very small segments

### 3. Enrichment Integration Tests (`surfaceEnrichment.test.ts`)

#### `calculateSurfaceBreakdownFromSegments`
- ✅ Calculates detailed breakdown from segments
- ✅ Converts detailed breakdown to simplified
- ✅ Handles segments with unknown surface type

#### `createSurfaceSegmentFeatures`
- ✅ Creates features with detailed surface types
- ✅ Maps features to simplified surface types

#### End-to-End Simplification Flow
- ✅ Correctly simplifies complete route with all surface types
- ✅ Verifies individual segment mapping
- ✅ Ensures data consistency across the pipeline

## Test Scenarios

### Scenario 1: Pure Paved Route
**Input**: 100% pavement  
**Expected**: 100% paved, 0% unpaved, 0% unknown

### Scenario 2: Pure Unpaved Route
**Input**: 50% gravel, 30% dirt, 20% singletrack  
**Expected**: 0% paved, 100% unpaved, 0% unknown

### Scenario 3: Mixed Route
**Input**: 40% pavement, 20% gravel, 15% dirt, 10% singletrack, 15% unknown  
**Expected**: 40% paved, 45% unpaved, 15% unknown

### Scenario 4: All Unknown Route
**Input**: 100% unknown  
**Expected**: 0% paved, 0% unpaved, 100% unknown

### Scenario 5: Real-World MTB Route
**Input**: 20% pavement, 0% gravel, 30% dirt, 40% singletrack, 10% unknown  
**Expected**: 20% paved, 70% unpaved, 10% unknown

## Validation Criteria

All tests verify:

1. **Correctness**: Mapping and aggregation produce expected results
2. **Completeness**: All surface types are handled
3. **Normalization**: Percentages always sum to 100
4. **Consistency**: Detailed data is preserved while simplified data is accurate
5. **Edge Cases**: Empty, invalid, and boundary conditions are handled

## Integration Points Tested

1. **Data Flow**: Detailed breakdown → Simplified breakdown
2. **Store Integration**: Segment data → Aggregated breakdown → Simplified breakdown
3. **Enrichment Integration**: Segments → Features → Simplified types
4. **Component Integration**: (Tested via unit tests, not E2E)

## Continuous Integration

These tests should be run:
- Before every commit (pre-commit hook recommended)
- In CI/CD pipeline on every PR
- Before releases
- After any changes to surface-related code

## Test Data

The tests use:
- **Mock segmented data**: Simulated route segments with known surface types
- **Real-world scenarios**: Breakdowns based on typical route patterns
- **Edge cases**: Boundary conditions and error states
- **Systematic coverage**: All combinations of surface types

## Expected Test Results

All tests should pass with:
- ✅ 100% pass rate
- ✅ No warnings or errors
- ✅ Coverage > 90% for surface-related code

## Debugging Failed Tests

If a test fails:

1. **Check the mapping**: Verify `mapSurfaceTypeToSimplified` returns correct values
2. **Check aggregation**: Verify `getSimplifiedSurfaceMix` correctly sums unpaved types
3. **Check normalization**: Verify percentages sum to 100
4. **Check edge cases**: Verify boundary conditions are handled
5. **Check data flow**: Verify data is not lost in conversion

## Future Enhancements

Potential additions to the test suite:

1. **Visual Regression Tests**: Screenshot comparison for UI components
2. **Performance Tests**: Verify aggregation performance on large routes
3. **E2E Tests**: Full user flow with surface coloring enabled
4. **Accessibility Tests**: Verify surface colors meet contrast requirements
5. **Data Quality Tests**: Verify enrichment reduces unknown percentage

## Related Files

- Implementation: `src/lib/surfaceMix.ts`
- Colors: `src/lib/surfaceColors.ts`
- Enrichment: `src/lib/surfaceEnrichment.ts`
- Store: `src/stores/surfaceStore.ts`
- Components: `src/components/inspector/ElevationChart.tsx`, `src/components/map/layers/RouteLayer.tsx`
