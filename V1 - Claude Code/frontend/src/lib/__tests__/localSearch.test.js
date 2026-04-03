const { getLocalIndexCandidates } = require('../localSearch');

describe('getLocalIndexCandidates', () => {
  const center = { lat: 30.2308, lng: -97.7688 };
  const localIndex = [
    { id: '1', label: 'Slaughter Lane', lat: 30.2301, lon: -97.8001, layer: 'street' },
    { id: '2', label: 'Slaughter Creek', lat: 30.1902, lon: -97.7405, layer: 'venue' },
    { id: '3', label: 'Barton Creek', lat: 30.2643, lon: -97.8424, layer: 'venue' },
  ];

  it('returns prefix matches for short queries', () => {
    const results = getLocalIndexCandidates({
      query: 'slau',
      localIndex,
      center,
      limit: 5,
    });
    expect(results.length).toBeGreaterThan(0);
    expect(results.some((item) => item.label === 'Slaughter Lane')).toBe(true);
  });

  it('returns contains matches when no prefix matches', () => {
    const results = getLocalIndexCandidates({
      query: 'creek',
      localIndex,
      center,
      limit: 5,
    });
    const labels = results.map((item) => item.label);
    expect(labels).toEqual(expect.arrayContaining(['Slaughter Creek', 'Barton Creek']));
  });

  it('sorts closer matches first', () => {
    const results = getLocalIndexCandidates({
      query: 'slaughter',
      localIndex,
      center,
      limit: 5,
    });
    expect(results[0].label).toBe('Slaughter Lane');
  });
});
