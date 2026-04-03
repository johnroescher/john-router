# Testing Guide

## Surface Type Testing

### Quick Reference

To test surface type simplification functionality, run:

```bash
npm run test:surface
```

Or use the full command:
```bash
npm test -- --testPathPattern="surface"
```

This will run all surface-related tests (42 tests across 3 test files).

### Surface Type Test Suite

The surface type simplification has a comprehensive test suite that verifies:

1. **Core Mapping Functions** (`src/lib/__tests__/surfaceMix.test.ts`)
   - Maps 5 detailed surface types to 3 simplified types
   - `pavement` → `paved`
   - `gravel`, `dirt`, `singletrack` → `unpaved`
   - `unknown` → `unknown`

2. **Store Integration** (`src/stores/__tests__/surfaceStore.test.ts`)
   - Segment aggregation
   - Detailed to simplified conversion
   - Edge cases

3. **Enrichment Integration** (`src/lib/__tests__/surfaceEnrichment.test.ts`)
   - Segment breakdown calculation
   - Feature creation with simplified types
   - End-to-end data flow

### Running Surface Type Tests

#### Run All Surface Tests
```bash
npm test -- --testPathPattern="surface"
```

#### Run Specific Test File
```bash
# Core mapping functions
npm test surfaceMix.test.ts

# Store integration
npm test surfaceStore.test.ts

# Enrichment integration
npm test surfaceEnrichment.test.ts
```

#### Run with Verbose Output
```bash
npm test -- --testPathPattern="surface" --verbose
```

#### Run in Watch Mode
```bash
npm run test:watch -- --testPathPattern="surface"
```

#### Run with Coverage
```bash
npm test -- --testPathPattern="surface" --coverage
```

### Expected Results

When all tests pass, you should see:

```
Test Suites: 3 passed, 3 total
Tests:       42 passed, 42 total
Snapshots:   0 total
Time:        ~0.4s
```

### Test Coverage

The test suite covers:

- ✅ All 5 surface types mapped correctly
- ✅ Aggregation of unpaved types (gravel + dirt + singletrack)
- ✅ Percentage normalization (always sums to 100)
- ✅ Edge cases (empty data, invalid percentages)
- ✅ Real-world route scenarios
- ✅ Store-level aggregation
- ✅ Enrichment integration
- ✅ End-to-end data flow

### Troubleshooting

If tests fail:

1. **Check TypeScript compilation**: `npm run build`
2. **Clear Jest cache**: `npm test -- --clearCache`
3. **Verify dependencies**: `npm install`
4. **Check test files exist**: All test files should be in `src/**/__tests__/`

### Related Documentation

- **Test Plan**: `TEST_PLAN_SURFACE_SIMPLIFICATION.md`
- **Test Summary**: `SURFACE_SIMPLIFICATION_TEST_SUMMARY.md`
- **Implementation Plan**: `../surface_type_simplification_5d847cef.plan.md`

---

## General Testing

### Run All Tests
```bash
npm test
```

### Routing Tests

#### Run route store + API trace tests
```bash
npm test routePointToPoint.test.ts
npm test routeStoreRouting.test.ts
```

#### Run backend smoke check (requires backend running)
```bash
npm run test:route-smoke
```

### Run Tests in Watch Mode
```bash
npm run test:watch
```

### Run Tests with Coverage
```bash
npm test -- --coverage
```

### Run Specific Test File
```bash
npm test <filename>
```

### Test Configuration

- **Jest Config**: `jest.config.js`
- **Jest Setup**: `jest.setup.js`
- **Test Pattern**: `**/__tests__/**/*.(test|spec).(ts|tsx|js)`
