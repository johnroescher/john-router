const run = async () => {
  const args = process.argv.slice(2);
  const lat = Number(args[0] || 30.23);
  const lng = Number(args[1] || -97.77);
  const prefix = String(args[2] || 'slau');
  const radiusKm = Number(args[3] || 40);

  const query = `[out:json][timeout:8];
(
  way["highway"]["name"~"^${prefix}",i](around:${Math.round(radiusKm * 1000)},${lat},${lng});
);
out tags center;`;

  const endpoints = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.nchc.org.tw/api/interpreter',
  ];

  let data = null;
  for (const endpoint of endpoints) {
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ data: query }),
      });
      if (!response.ok) {
        console.warn('Overpass error:', response.status, 'for', endpoint);
        continue;
      }
      data = await response.json();
      break;
    } catch (error) {
      console.warn('Overpass request failed for', endpoint, error);
    }
  }

  if (!data) {
    console.error('No Overpass endpoint succeeded.');
    return;
  }
  const names = (data?.elements || [])
    .map((el) => el?.tags?.name)
    .filter(Boolean);

  console.log(`Prefix matches for "${prefix}" near ${lat}, ${lng} (radius ${radiusKm}km):`);
  console.log(names.slice(0, 20));
};

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
