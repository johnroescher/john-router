/**
 * Utility to generate diverse suggested chat prompts
 */

interface PromptCategory {
  prompts: string[];
  weight: number;
}

interface PromptOptions {
  count?: number;
  ridiculousnessLevel?: number;
  usedPrompts?: string[];
}

const emojiRules: Array<{ emoji: string; keywords: string[] }> = [
  { emoji: '⚡️', keywords: ['e-bike', 'e-bikes', 'quick'] },
  { emoji: '🚵', keywords: ['mountain bike', 'mtb', 'singletrack', 'technical', 'trail'] },
  { emoji: '🪨', keywords: ['gravel', 'rocky'] },
  { emoji: '🚴', keywords: ['road', 'paved'] },
  { emoji: '🌄', keywords: ['scenic', 'views', 'ridge'] },
  { emoji: '🌲', keywords: ['forest'] },
  { emoji: '🌊', keywords: ['water', 'lake'] },
  { emoji: '⛰️', keywords: ['mountain', 'climb', 'steep', 'elevation'] },
  { emoji: '🏁', keywords: ['endurance', 'epic'] },
  { emoji: '🔁', keywords: ['loop'] },
  { emoji: '🛑', keywords: ['rest stop', 'rest stops'] },
  { emoji: '🚗', keywords: ['traffic'] },
];

const addEmojiPrefix = (prompt: string): string => {
  const lower = prompt.toLowerCase();
  const match = emojiRules.find((rule) => rule.keywords.some((keyword) => lower.includes(keyword)));
  const emoji = match ? match.emoji : '🚴';
  return `${emoji} ${prompt}`;
};

// General prompts with location references
const locationCategories: PromptCategory[] = [
  {
    prompts: [
      'Plan a 2-hour mountain bike ride near me',
      'Looking for a 3-hour gravel adventure in my area',
      'Design a 90-minute road cycling route around here',
      'Build a 4-hour epic MTB loop near my location',
      'Any chance for a 1.5-hour flow trail ride close to my location',
      'A 2.5-hour mixed terrain route nearby would be great',
    ],
    weight: 1,
  },
  {
    prompts: [
      'Create a 20-mile route with maximum singletrack near me',
      'I want a 15-mile route avoiding busy roads in my area',
      'Plan a short route with minimal climbing around here',
      'A long route with challenging climbs near my location sounds great',
      'Design a 25-mile route with scenic views nearby',
      'Could you put together a 30-mile route with technical descents close to my location',
    ],
    weight: 1,
  },
  {
    prompts: [
      'Plan a beginner-friendly 10-mile route near me',
      'An advanced technical 40-mile route in my area would be ideal',
      'Design a long route for endurance training around here',
      'Build a short route for interval training nearby',
      'Is there a 18-mile route suitable for e-bikes near my location',
      'Plan a 3-hour route with multiple rest stops close to my location',
    ],
    weight: 1,
  },
  {
    prompts: [
      'Create a 22-mile route with varied terrain near me',
      'Plan a 2-hour route through forests in my area',
      'A short route with water crossings around here sounds fun',
      'Build a long route with ridge riding nearby',
      'Looking for a 12-mile route with smooth descents near my location',
      'Plan a 35-mile route with technical features close to my location',
    ],
    weight: 1,
  },
  {
    prompts: [
      'Find a 28-mile route with minimal elevation near me',
      'Create a 2.5-hour route with steep sections in my area',
      'A 16-mile route perfect for beginners around here would be great',
      'Build a 45-mile epic adventure nearby',
      'Just a 1-hour quick ride near my location today',
      'Find a 50-mile endurance challenge close to my location',
    ],
    weight: 1,
  },
];

// Location-based prompts (implicit/relative location references)
const implicitLocationPrompts = [
  'Plan a 2-hour ride starting from my location',
  'Create a 20-mile route from here with minimal traffic',
  'Looking for a short loop starting from my current location',
  'A long route from here with scenic views would be awesome',
  'Design a 15-mile route starting from my location',
  'Plan a 3-hour adventure from my location',
  'Any 25-mile route near me?',
  'I want a 2.5-hour ride close to my location',
  'A route near a lake sounds perfect',
  'Find a 18-mile route close to water',
  'Build a route near mountains',
  'A 30-mile route starting near me would be ideal',
];

// Location-based prompts (explicit landmarks/towns/parks)
const explicitLocationPrompts = [
  'Plan a 2-hour ride in Pisgah National Forest',
  'A 20-mile route near Boulder, Colorado would be great',
  'Find a 3-hour loop in Moab',
  'Build a 25-mile route through Sedona',
  'A 2.5-hour ride in Whistler sounds perfect',
  'Plan a 30-mile route in Marin County',
  'Looking for a 15-mile loop near Bend, Oregon',
  'Create a 3-hour adventure in Park City',
  'Build a 22-mile route through the Blue Ridge Mountains',
  'A route near Lake Tahoe would be amazing',
  'Find a 18-mile loop in the San Juan Mountains',
  'Design a 2-hour ride in the White Mountains',
];

const locationPhrases = [
  'near me',
  'around here',
  'close to my location',
  'nearby',
  'from here',
  'in my area',
];

const ridiculousPrefixTiers = [
  [],
  ['Quick favor: ', 'Just for fun, ', 'Okay, but make it: '],
  ['Plot twist: ', 'For science, ', 'Behold: '],
  ['Legend says: ', 'In a parallel universe, ', 'Summon the vibes: '],
];

const ridiculousSuffixTiers = [
  [],
  [
    ' with a coffee stop',
    ' with a snack break built in',
    ' timed for golden hour',
    ' that ends at a bakery',
    ' with bonus viewpoint time',
  ],
  [
    ' that maximizes donut opportunities',
    ' with a "wave at cows" detour',
    ' that earns me a high-five',
    ' with a second-breakfast out-and-back',
    ' that keeps the vibes immaculate',
  ],
  [
    ' that traces the outline of a dinosaur',
    ' with only left turns and dramatic poses',
    ' that ends exactly at taco time',
    ' with a mystical fog bonus if available',
    ' that makes my GPS question reality',
  ],
  [
    ' that spells LOL on the map',
    ' guided entirely by vibes and a coin flip',
    ' with a side quest to find a wizard',
    ' for the glory of mountain goats',
    ' that bends the space-time biking continuum',
  ],
];

const ridiculousStandaloneTemplates = [
  'Design a route {location} that looks like a taco on the map',
  'Plan a ride {location} that hits three coffee shops and one mysterious statue',
  'Create a loop {location} shaped vaguely like a llama',
  'Build a route {location} that avoids all right turns',
  'Plan a route {location} that passes every overlook and a lemonade stand',
  'Design a ride {location} that ends exactly at sunset with dramatic flair',
  'Create a route {location} that feels like a quest log from a fantasy game',
  'Plan a route {location} for maximum giggles per mile',
];

const getRandomItem = <T,>(items: T[]): T => items[Math.floor(Math.random() * items.length)];

const getRidiculousTier = (level: number): number => {
  if (level >= 10) return 4;
  if (level >= 6) return 3;
  if (level >= 3) return 2;
  if (level >= 1) return 1;
  return 0;
};

const applyRidiculousness = (prompt: string, level: number): string => {
  const tier = getRidiculousTier(level);
  if (tier === 0) return prompt;
  const prefixPool = ridiculousPrefixTiers[Math.min(tier, ridiculousPrefixTiers.length - 1)];
  const suffixPool = ridiculousSuffixTiers[Math.min(tier, ridiculousSuffixTiers.length - 1)];
  const prefix = prefixPool.length > 0 && Math.random() < 0.35 ? getRandomItem(prefixPool) : '';
  const suffix = suffixPool.length > 0 ? getRandomItem(suffixPool) : '';
  return `${prefix}${prompt}${suffix}`;
};

const getRidiculousStandalonePrompt = (level: number): string => {
  const tier = getRidiculousTier(level);
  const templatePool = tier >= 3 ? ridiculousStandaloneTemplates : ridiculousStandaloneTemplates.slice(0, 4);
  const template = getRandomItem(templatePool);
  return template.replace('{location}', getRandomItem(locationPhrases));
};

/**
 * Generates 10 diverse suggested prompts
 * All prompts include a location reference (explicit or implicit)
 */
export function generateSuggestedPrompts(
  mapCenter?: { lat: number; lng: number } | null,
  options: PromptOptions = {}
): string[] {
  const count = options.count ?? 10;
  const ridiculousnessLevel = options.ridiculousnessLevel ?? 0;
  const usedPrompts = new Set<string>(options.usedPrompts ?? []);
  const prompts: string[] = [];
  const maxAttempts = count * 12;

  // Helper to get a random prompt from a category
  const getRandomPrompt = (category: PromptCategory, categoryIdx: number): string => {
    const available = category.prompts.filter((prompt) => !usedPrompts.has(prompt));
    
    if (available.length === 0) {
      // Fallback to any prompt from category
      const randomIdx = Math.floor(Math.random() * category.prompts.length);
      return category.prompts[randomIdx];
    }
    
    const randomPrompt = available[Math.floor(Math.random() * available.length)];
    usedPrompts.add(randomPrompt);
    return randomPrompt;
  };

  // Helper to get a random location prompt
  const getRandomLocationPrompt = (promptList: string[]): string => {
    const available = promptList.filter((prompt) => !usedPrompts.has(prompt));
    
    if (available.length === 0) {
      // Fallback to any prompt
      const randomIdx = Math.floor(Math.random() * promptList.length);
      return promptList[randomIdx];
    }
    
    const randomPrompt = available[Math.floor(Math.random() * available.length)];
    usedPrompts.add(randomPrompt);
    return randomPrompt;
  };

  const locationPrompts: string[] = [];
  const firstIsImplicit = mapCenter ? true : Math.random() < 0.5;
  if (count >= 1) {
    if (firstIsImplicit) {
      locationPrompts.push(getRandomLocationPrompt(implicitLocationPrompts));
    } else {
      locationPrompts.push(getRandomLocationPrompt(explicitLocationPrompts));
    }
  }
  if (count >= 2) {
    if (firstIsImplicit) {
      locationPrompts.push(getRandomLocationPrompt(explicitLocationPrompts));
    } else {
      locationPrompts.push(getRandomLocationPrompt(implicitLocationPrompts));
    }
  }

  const flavoredLocationPrompts = locationPrompts.map((prompt) => applyRidiculousness(prompt, ridiculousnessLevel));
  flavoredLocationPrompts.forEach((prompt) => usedPrompts.add(prompt));
  prompts.push(...flavoredLocationPrompts);

  const selectedCategories = new Set<number>();
  let attempts = 0;
  while (prompts.length < count && attempts < maxAttempts) {
    attempts += 1;
    const useStandalone =
      ridiculousnessLevel >= 2 &&
      Math.random() < Math.min(0.15 + ridiculousnessLevel * 0.03, 0.6);

    let nextPrompt = '';

    if (useStandalone) {
      nextPrompt = getRidiculousStandalonePrompt(ridiculousnessLevel);
    } else {
      let categoryIdx: number;
      if (selectedCategories.size < locationCategories.length) {
        do {
          categoryIdx = Math.floor(Math.random() * locationCategories.length);
        } while (selectedCategories.has(categoryIdx));
        selectedCategories.add(categoryIdx);
      } else {
        categoryIdx = Math.floor(Math.random() * locationCategories.length);
      }
      nextPrompt = getRandomPrompt(locationCategories[categoryIdx], categoryIdx);
    }

    nextPrompt = applyRidiculousness(nextPrompt, ridiculousnessLevel);
    if (!usedPrompts.has(nextPrompt)) {
      usedPrompts.add(nextPrompt);
      prompts.push(nextPrompt);
    }
  }

  while (prompts.length < count) {
    const fallback = applyRidiculousness(getRandomPrompt(getRandomItem(locationCategories), 0), ridiculousnessLevel);
    usedPrompts.add(fallback);
    prompts.push(fallback);
  }

  // Shuffle the array so location prompts aren't always first
  for (let i = prompts.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [prompts[i], prompts[j]] = [prompts[j], prompts[i]];
  }

  return prompts.map(addEmojiPrefix);
}
