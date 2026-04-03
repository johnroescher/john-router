const normalizeText = (value) =>
  value
    .toLowerCase()
    .replace(/[^\w\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const getDistanceKm = (from, to) => {
  const toRad = (val) => (val * Math.PI) / 180;
  const earthRadiusKm = 6371;
  const dLat = toRad(to.lat - from.lat);
  const dLng = toRad(to.lng - from.lng);
  const lat1 = toRad(from.lat);
  const lat2 = toRad(to.lat);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.sin(dLng / 2) ** 2 * Math.cos(lat1) * Math.cos(lat2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return earthRadiusKm * c;
};

const getLocalIndexCandidates = ({ query, localIndex, center, limit = 5 }) => {
  if (!center || !query || !Array.isArray(localIndex)) return [];
  const normalizedQuery = normalizeText(query);
  if (normalizedQuery.length < 2) return [];
  const prefixMatches = localIndex.filter((item) =>
    item.label.toLowerCase().startsWith(normalizedQuery)
  );
  const containsMatches = localIndex.filter((item) =>
    item.label.toLowerCase().includes(normalizedQuery)
  );
  const candidates = prefixMatches.length > 0 ? prefixMatches : containsMatches;
  if (candidates.length === 0) return [];
  return candidates
    .map((item) => ({
      ...item,
      distanceKm: getDistanceKm(center, { lat: item.lat, lng: item.lon }),
    }))
    .sort((a, b) => {
      if (a.distanceKm !== b.distanceKm) return a.distanceKm - b.distanceKm;
      return a.label.length - b.label.length;
    })
    .slice(0, limit);
};

module.exports = {
  normalizeText,
  getDistanceKm,
  getLocalIndexCandidates,
};
