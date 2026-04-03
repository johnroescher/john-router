# John Router - Comprehensive Product Documentation

## Executive Summary

**John Router** is an AI-powered cycling route planning application that revolutionizes how cyclists discover and plan their perfect ride—whatever that means to them. By combining conversational AI with professional-grade mapping tools, John Router makes world-class route planning accessible to all cyclists, honoring the diverse and deeply personal nature of cycling: mountain biking, gravel grinding, road racing, urban rambling, bikepacking adventures, endurance challenges, and everything in between.

### Product Vision

To become the world's most intelligent and trusted route planning tool for all cyclists, recognizing that every ride—from a technical singletrack to a quiet coffee shop cruise—deserves the same level of thoughtful planning and personalization.

### Mission Statement

Empower every cyclist to explore confidently by providing transparent, data-driven route planning that celebrates the diversity of cycling and prioritizes safety, accuracy, and the joy of discovering rides perfectly tailored to individual preferences, abilities, and what brings them happiness on two wheels.

---

## Problem Statement

### Current Market Gaps

1. **One-Size-Fits-All Approach**: Existing routing tools treat all cycling the same, failing to recognize that a road cyclist's needs differ vastly from a mountain biker's, and both differ from an urban explorer's or bikepacker's requirements.

2. **Inadequate Terrain Intelligence**: Current solutions don't distinguish between surface nuances—a smooth gravel path vs. technical singletrack, a bike lane vs. sharrow on busy street, a quiet backroad vs. highway shoulder—leading to mismatches between rider preferences and route reality.

3. **Static Route Planning**: Traditional tools require manual waypoint placement and offer limited ability to express preferences in natural language ("I want a peaceful 2-hour ramble through quiet neighborhoods with a bakery stop").

4. **Opaque AI Decisions**: When AI is used, it acts as a black box without explaining why certain routes were chosen or what trade-offs were made.

5. **Poor Data Quality**: Routes often include impossible segments (private property, closed paths, unsafe traffic exposure, unrideable terrain) due to inadequate validation across all cycling contexts.

### Pain Points by User Type

**Mountain Bikers**
- Can't filter routes by technical difficulty (mtb:scale ratings)
- Get routed onto hike-a-bike sections unintentionally
- No warning about technical features (rock gardens, drops, exposure)
- Difficulty finding trails matching skill level in unfamiliar areas

**Gravel Riders**
- Unclear surface composition (is it smooth gravel or chunky?)
- Routes include paved sections without warning
- No way to specify desired pavement/gravel ratio
- Traffic exposure on road connections

**Road Cyclists**
- Routed onto busy highways without bike infrastructure
- Can't find quiet backroads with good pavement quality
- Limited control over elevation profiles for training rides
- No integration with coffee shop culture and social stops

**Urban Adventurers & Ramblers**
- Want scenic, exploratory routes through interesting neighborhoods
- Need to avoid dangerous intersections and high-traffic corridors
- Desire routes that connect parks, greenways, and cultural points
- Can't express "vibe" preferences (quiet, historic, waterfront, etc.)

**Bikepacking & Touring**
- Can't easily plan multi-day routes with service point spacing
- No integration of campsite, water source, and resupply data
- Difficulty balancing daily distance with terrain difficulty
- Remote area navigation challenges

**Endurance & Training Cyclists**
- Need specific elevation profiles and interval segments
- Want routes that match power/heart rate zones
- Difficulty planning progressive training routes
- Limited nutrition/hydration stop integration

**All Cyclists**
- Want to explore new variations of familiar areas
- Need current condition information (construction, closures, surface changes)
- Desire seasonal route recommendations
- Struggle to articulate preferences to existing tools

---

## Target Audience

### Primary User Personas

#### 1. **Technical Trail Seeker - "Sarah"**
- **Age**: 32
- **Location**: Boulder, Colorado
- **Skill Level**: Advanced MTB, Intermediate Road
- **Bike**: Full-suspension trail bike (130mm)
- **Typical Ride**: 2-3 hour technical singletrack loops
- **Pain Points**:
  - Wants challenging terrain but not beyond her skill level
  - Needs to know if trails have features she's uncomfortable with (exposure, large drops)
  - Traveling to new areas and needs accurate difficulty information
  - Frustrated by routes that include long pavement connectors
- **Goals**:
  - Find new trails that match her "flowy with some chunk" preference
  - Plan trips to MTB destinations with confidence
  - Avoid crowds by finding alternative routes
- **Quote**: "I love technical riding but hate surprises. I need to know exactly what I'm getting into."

#### 2. **Gravel Explorer - "Marcus"**
- **Age**: 45
- **Location**: Portland, Oregon
- **Skill Level**: Intermediate Gravel, Advanced Road
- **Bike**: Carbon gravel bike with 42mm tires
- **Typical Ride**: 3-4 hour gravel adventures, 40-60 miles
- **Pain Points**:
  - Struggles to find the "sweet spot" of rideable gravel
  - Routes from other apps often include rough 4x4 roads
  - Wants scenic routes but doesn't know where the views are
  - Needs reliable surface information for tire choice
- **Goals**:
  - Discover new gravel roads with <20% pavement
  - Plan all-day epics with coffee shop stops
  - Share routes with friends who have different fitness levels
- **Quote**: "I want adventure, not survival. Give me challenging but rideable gravel."

#### 3. **Weekend Warrior - "Jessica"**
- **Age**: 28
- **Location**: Austin, Texas
- **Skill Level**: Beginner MTB, Intermediate Road
- **Bike**: Hardtail XC bike
- **Typical Ride**: 1-2 hour easy to moderate trails
- **Pain Points**:
  - Intimidated by overly technical trails
  - Wants progression but safely
  - Doesn't understand trail rating systems
  - Worried about getting lost or stranded
- **Goals**:
  - Build confidence on progressively harder terrain
  - Find beginner-friendly group ride routes
  - Learn about trails before showing up
- **Quote**: "I love mountain biking but I'm still learning. I need routes that won't be over my head."

#### 4. **Destination Planner - "David"**
- **Age**: 38
- **Location**: San Francisco, CA (travels frequently)
- **Skill Level**: Advanced All-Around
- **Bikes**: MTB, Gravel, Road
- **Typical Ride**: Planning upcoming trips
- **Pain Points**:
  - Hard to find current condition information
  - Doesn't know which trails are "must-ride" in new areas
  - Rental bike selection depends on terrain
- **Goals**:
  - Understand seasonal considerations
  - Get the "insider knowledge" without being a local
- **Quote**: "I only have 3 days in Moab. I need to nail the route selection."

#### 5. **Urban Rambler - "Chen"**
- **Age**: 29
- **Location**: Brooklyn, New York
- **Skill Level**: Intermediate Urban Cycling
- **Bike**: Steel city bike with fenders and rack
- **Typical Ride**: 1-2 hour exploratory rides through neighborhoods
- **Pain Points**:
  - Existing tools prioritize speed/distance, not discovery and "vibe"
  - Hard to find safe, pleasant routes that avoid dangerous streets
  - Wants to discover new cafes, parks, and interesting streets
  - Tired of the same commute routes
- **Goals**:
  - Explore different neighborhoods safely and leisurely
  - Find scenic routes that connect cultural destinations
  - Discover new local spots (bookstores, bakeries, murals)
  - Share "hidden gem" routes with friends
- **Quote**: "I don't want the fastest route, I want the most interesting one. Show me the soul of the city."

#### 6. **Road Training Enthusiast - "Priya"**
- **Age**: 42
- **Location**: Austin, Texas
- **Skill Level**: Advanced Road Cyclist
- **Bike**: Carbon road bike, power meter equipped
- **Typical Ride**: 2-4 hour training rides, 40-80 miles
- **Pain Points**:
  - Needs specific elevation profiles for interval training
  - Wants low-traffic roads but doesn't know where they are
  - Planning century routes with proper bailout points is tedious
  - Can't easily find routes matching power zone targets
- **Goals**:
  - Build progressive training routes with specific climbing
  - Find safe roads for high-intensity efforts
  - Plan long-distance rides with support stops
  - Train effectively for upcoming events
- **Quote**: "I need routes that match my training plan, not just random loops. Give me 2,000ft of climbing with a coffee stop at mile 40."

#### 7. **Bikepacking Adventurer - "Alex"**
- **Age**: 35
- **Location**: Denver, Colorado
- **Skill Level**: Advanced Mixed Terrain
- **Bike**: Gravel bike with bikepacking bags
- **Typical Ride**: Multi-day adventures, 50-100 miles per day
- **Pain Points**:
  - Multi-day route planning is incredibly time-consuming
  - Hard to find water sources, camping, and resupply points
  - Mixed terrain analysis across days is difficult
  - Need to balance daily distance with loaded bike capabilities
- **Goals**:
  - Plan 3-7 day routes with proper daily segments
  - Identify water, camping, and food options
  - Assess terrain suitability for loaded riding
  - Discover remote routes with necessary infrastructure
- **Quote**: "I need to know where I can fill water bottles and camp legally. Pretty views are great, but logistics keep me alive."

### Secondary Audiences

- **Cycling Coaches**: Planning training routes with specific elevation and intensity profiles
- **Bike Shop Employees**: Recommending rides to customers and tourists
- **Event Organizers**: Scouting and designing race/gran fondo courses
- **Tourism Boards**: Showcasing regional cycling opportunities
- **Cycling Media**: Planning locations for articles and videos

---

## Product Overview

### Core Value Propositions

1. **Chat-First Interface**: Describe your ideal ride in plain English—whether that's "technical singletrack," "quiet neighborhood ramble," or "century with climbing"—and let AI translate into optimized routes
2. **Every Ride Matters**: From technical trail features to bike lane quality to neighborhood vibes, every detail relevant to your style of cycling is first-class data, analyzed with equal care
3. **Professional Controls**: Full manual override with drag-and-drop route editing, waypoint locking, and avoidance areas—accessible to beginners, powerful for experts
4. **Transparent Intelligence**: AI explains its decisions, shows confidence levels, and cites data sources—you understand why routes were chosen and what trade-offs exist
5. **Quality Over Speed**: Multi-candidate generation with full validation ensures you get great routes, not just fast answers—safety and accuracy never compromised

### Unique Differentiators

| Feature | John Router | Komoot | Strava Routes | RideWithGPS | Trailforks |
|---------|-------------|--------|---------------|-------------|------------|
| AI Chat Interface | ✅ Full NL understanding | ❌ | ❌ | ❌ | ❌ |
| All-Cycling Intelligence | ✅ MTB, Road, Gravel, Urban | ⚠️ Basic | ⚠️ Road-focused | ⚠️ Basic | ⚠️ MTB-only |
| Surface & Terrain Analysis | ✅ Detailed, contextual | ⚠️ Binary | ❌ | ⚠️ Basic | ✅ Trail-only |
| Route Validation | ✅ Comprehensive, multi-discipline | ⚠️ Basic | ⚠️ Basic | ✅ | ⚠️ Trail-only |
| Quality Mode | ✅ Multi-candidate | ❌ | ❌ | ❌ | ❌ |
| Professional Editing | ✅ Full control | ✅ | ⚠️ Limited | ✅ | ❌ |
| Explain Mode | ✅ Transparent AI | ❌ | ❌ | ❌ | ❌ |

---

## Core Features & Capabilities

### 1. Conversational AI Copilot

**Description**: Chat-based interface powered by Claude AI that understands cycling terminology and preferences to generate and refine routes through natural conversation.

**Capabilities**:
- Natural language route requests ("2-hour MTB ride with flowy singletrack")
- Iterative refinement ("Make it less technical", "Add a coffee stop")
- Preference learning and memory within conversation
- Context awareness of current route and user history
- Multi-turn reasoning for complex requests
- Automatic constraint extraction from free-form descriptions

**Technical Implementation**:
- Claude 3.5 Sonnet API integration
- Custom prompt engineering for cycling domain
- Tool calling for geocoding, routing, and validation
- Streaming responses for real-time feedback
- Conversation state management with PostgreSQL storage

**User Stories**:
- As a user, I can say "plan a 30-mile gravel loop from Austin" and get a complete route
- As a user, I can refine routes by saying "avoid highways" or "add more climbing"
- As a user, I can ask "why did you choose this route?" and get a detailed explanation
- As a user, I can request "find the best singletrack near Boulder" without knowing trail names

### 2. Comprehensive Cycling Intelligence

**Description**: Deep, contextual analysis of routes tailored to each cycling discipline—understanding that a road cyclist cares about pavement quality and traffic, a mountain biker needs technical ratings, a gravel rider wants surface composition, and an urban explorer seeks neighborhood character.

**Capabilities**:

**For Mountain Bikers**:
- **MTB Difficulty Ratings**: OSM mtb:scale (0-6+) mapped to standard trail colors:
  - mtb:scale 0 → Green (Easy)
  - mtb:scale 1 → Blue (Intermediate)
  - mtb:scale 2 → Black (Difficult)
  - mtb:scale 3+ → Double Black (Expert)
- **Technical Features**: Detection and warning for rock gardens, roots, drops, jumps, exposure, loose terrain, water crossings
- **Hike-a-Bike Detection**: Identifies unrideable sections (>25% grade, obstacles, steps)
- **Flow Analysis**: Trail character assessment (flowy, technical, chunky)

**For Road Cyclists**:
- **Traffic Analysis**: Vehicle volume, speed limits, shoulder width
- **Bike Infrastructure**: Protected lanes, bike lanes, sharrows, cycling routes
- **Pavement Quality**: Surface condition and smoothness ratings
- **Road Classification**: Quiet backroads vs. busy arterials vs. highways
- **Intersection Safety**: Complex/dangerous crossing identification
- **Climb Analysis**: Categorized climbs (Cat 4 to HC), gradient profiles

**For Gravel Riders**:
- **Surface Breakdown**: Percentage analysis across pavement, gravel, dirt, singletrack
- **Gravel Quality**: Compacted vs. loose, chunky vs. smooth
- **Tire Suitability**: Analysis for different tire widths
- **Seasonal Variability**: Mud potential, washboard conditions
- **Scenic Quality**: Remote roads, views, backcountry character

**For Urban Cyclists**:
- **Neighborhood Character**: Quiet residential, commercial, industrial, parkways
- **Points of Interest**: Cafes, parks, cultural sites, greenways
- **Safety Assessment**: Well-lit streets, pedestrian activity levels
- **Traffic Stress**: Low-stress vs. high-stress streets
- **Infrastructure**: Bike lanes, cycletracks, protected paths, greenways

**For All Cyclists**:
- **Physical Difficulty**: Combines distance, elevation, and grade into fitness score
- **Risk Rating**: Remoteness, hazards, and exposure assessment
- **Confidence Scores**: Data completeness and quality assessment
- **Validation Status**: Safety, legality, and rideability checks

**Data Sources**:
- OpenStreetMap: mtb:scale, surface tags, trail features
- OpenRouteService: Base routing and elevation
- Digital Elevation Models: Grade analysis
- Trail organization APIs (future): Real-time conditions

**User Stories**:
- As a beginner MTB rider, I can filter routes to only show green and blue trails
- As a road cyclist, I can see which segments have bike lanes vs. riding on the shoulder
- As a gravel rider, I can specify "80% gravel, 20% pavement" and get matching routes
- As an urban cyclist, I can route through quiet neighborhoods and avoid busy arterials
- As a bikepacker, I can see where surfaces change from pavement to gravel to help plan tire pressure
- As a training cyclist, I can find roads with long, steady climbs suitable for intervals
- As a cautious rider, I can exclude routes with exposure, high-traffic roads, or dangerous intersections
- As any cyclist, I understand the data confidence level and can make informed decisions

### 3. Professional Route Editor

**Description**: Full-featured map interface with manual controls for precision route planning.

**Capabilities**:
- **Interactive Map**:
  - MapLibre GL JS rendering
  - Multiple base layers (topo, satellite, street)
  - Route drag-and-drop adjustment
  - Click to add waypoints
  - Context menus for segment operations
- **Waypoint Management**:
  - Typed waypoints (start, end, via, POI, coffee, water, restroom, viewpoint, bike_shop)
  - Soft locks (AI can move slightly)
  - Hard locks (fixed position)
  - Reorder and delete waypoints
  - Snap to roads/trails
- **Avoidance Areas**:
  - Draw polygon areas to avoid
  - Named avoidance zones (save for reuse)
  - Private property overlay
  - Seasonal closure integration
- **Route Constraints Panel**:
  - Distance targets and limits
  - Elevation gain targets
  - Time constraints
  - Route type (loop, out-and-back, point-to-point)
  - Sport type selection with profile presets
  - Surface preferences sliders
  - Technical difficulty limits
  - Hazard avoidances toggles
- **Inspector Panel**:
  - Elevation profile with grade overlay
  - Surface breakdown chart
  - Difficulty breakdown
  - Segment-by-segment details
  - Validation issue list with locations
  - Export options (GPX, TCX, KML)

**Technical Implementation**:
- MapLibre GL JS with custom controls
- GeoJSON route geometry
- Zustand state management
- Real-time constraint validation
- Optimistic UI updates with rollback
- Debounced re-routing on edits

**User Stories**:
- As a user, I can drag the route to follow a specific road I know is scenic
- As a user, I can lock waypoints that must stay fixed while the AI optimizes the rest
- As a user, I can draw an area around private property to ensure routes avoid it
- As a user, I can manually add a coffee shop stop and have the route re-optimize
- As a user, I can export routes to my Garmin/Wahoo device

### 4. Quality Mode with Multi-Candidate Generation

**Description**: Advanced routing pipeline that generates multiple route options, validates each, and presents the best candidates with transparent trade-off analysis.

**How It Works**:
1. **Constraint Interpretation**: AI converts user request into structured constraints
2. **Candidate Generation**: Generate 3-5 route variations with different optimizations:
   - Shortest distance
   - Most scenic (elevation/views)
   - Least elevation gain
   - Most off-road
   - Balanced (multi-objective optimization)
3. **Comprehensive Analysis**: Each candidate receives:
   - Full elevation and surface analysis
   - Difficulty scoring
   - Safety and legality validation
   - Data completeness assessment
4. **Ranking & Scoring**: Candidates ranked by:
   - Constraint satisfaction (hard constraints must pass)
   - Preference alignment (soft preferences scored)
   - Data confidence (higher data quality ranked higher)
   - Safety and legality (issues penalized)
5. **Presentation**: Top 3 candidates shown with:
   - Side-by-side comparison
   - Trade-off explanation (e.g., "Route A is 2 miles shorter but has 500ft more climbing")
   - AI recommendation with reasoning

**Settings**:
- Quality Mode: On/Off (default: On)
- Number of candidates: 1-5 (default: 3)
- Time limit: 10-30 seconds (default: 20s)

**User Stories**:
- As a user, I receive 3 route options and can see the pros/cons of each
- As a user, I understand why Route A was recommended over Route B
- As a user, I can switch between candidates without re-generating
- As a user, I can disable quality mode for faster results when exploring

### 5. Comprehensive Route Validation

**Description**: Multi-layered validation system that checks routes for safety, legality, rideability, and data quality issues.

**Validation Checks**:

**Connectivity Validation**:
- Gap detection: No gaps >500m between segments
- Bridge identification: Ensures river crossings exist
- Tunnel detection: Verifies tunnel access for bikes
- Private property: Checks for routing through restricted areas

**Legality Validation**:
- Bicycle access: All segments must allow bicycles
- Trail designations: MTB routes only use MTB-legal trails
- Restricted areas: National parks, wilderness areas compliance

**Safety Validation**:
- Grade limits: Warns about extreme grades (>15% up, >20% down)
- Traffic exposure: High-speed road warnings
- Nighttime safety: Lighting, remoteness for night rides
- Exposure warnings: Cliff edges, drop-offs
- Water hazards: Unbridged river crossings

**Difficulty Validation**:
- Skill mismatch: Route difficulty vs. user skill level
- Fitness check: Distance/elevation vs. user fitness
- Technical features: Warnings for features user wants to avoid
- Surface appropriateness: Bike type vs. terrain

**Data Quality Validation**:
- Completeness score: Percentage of route with full data
- Confidence assessment: How certain is the routing engine?
- Missing data warnings: Segments with no surface/difficulty data
- Elevation data quality: Accuracy of elevation profile

**Issue Severity Levels**:
- **Error** (red): Route is unsafe or illegal, must fix
- **Warning** (yellow): Potential issue, user should review
- **Info** (blue): FYI, not necessarily a problem

**Fix Suggestions**:
- For each validation issue, AI suggests fixes:
  - "Route segment crosses private property. Suggest rerouting 200m north."
  - "Grade exceeds 20% for 0.3mi. Consider alternative climb."
  - "No bike access on Hwy 101. Use parallel bike path instead."

**User Stories**:
- As a user, I am warned before creating a route on a closed trail
- As a user, I see validation errors highlighted on the map with locations
- As a user, I receive fix suggestions that I can accept with one click
- As a user, I understand data confidence and can make informed decisions

### 7. Multi-Discipline Routing Intelligence

**Description**: Discipline-specific routing algorithms and constraints that deeply understand what makes a great ride for each style of cycling—because a perfect road route differs fundamentally from a perfect MTB trail or urban ramble.

**Supported Cycling Disciplines**:

**Road Cycling**:
- **Preferences**: Smooth pavement, bike lanes/shoulders, low-traffic backroads, scenic byways
- **Avoids**: Unpaved roads, trails, dangerous highways, poor pavement, high-traffic roads
- **Optimization**: Distance efficiency, elevation profiles for training, smooth road surfaces
- **Special Features**: Coffee shop routing, group ride pace consideration, century planning, climb categorization
- **Intelligence**: Understands difference between a quiet country road and a busy arterial with bike lane

**Gravel Cycling**:
- **Preferences**: Gravel roads, dirt roads, rail trails, doubletrack, maintained forest roads
- **Avoids**: Pavement (configurable %), technical singletrack, 4x4 roads, loose/chunky surfaces
- **Optimization**: Surface quality, scenic remote roads, adventure character
- **Special Features**: Tire width recommendations, escape route planning, mixed-surface transitions
- **Intelligence**: Distinguishes smooth compacted gravel from rough chunky roads; considers seasonality

**Mountain Biking (MTB)**:
- **Preferences**: Singletrack, designated MTB trails, flow trails, bike parks
- **Avoids**: Pavement, hike-a-bike, technical features beyond skill level, illegal trails
- **Optimization**: Flow, technical challenge matching skill, trail ratings, fun factor
- **Special Features**: Shuttle vs. pedal routes, trail network optimization, descent maximization
- **Intelligence**: Understands trail character (flowy vs. chunky), technical feature context

**eMTB (Electric Mountain Bike)**:
- **Preferences**: Steeper climbs accessible, longer distances, mixed terrain
- **Avoids**: eMTB restrictions, non-motorized wilderness areas
- **Optimization**: Maximize descent, battery-efficient routing, longer range planning
- **Special Features**: Battery range estimation, charging station routing, climb-focused routes
- **Intelligence**: Factors in motor assistance for realistic range and elevation planning

**Urban & Adventure Cycling**:
- **Preferences**: Quiet streets, bike lanes, greenways, parks, interesting neighborhoods
- **Avoids**: High-traffic arterials, dangerous intersections, highways, industrial corridors
- **Optimization**: Low-stress routing, points of interest, scenic/cultural exploration
- **Special Features**: Neighborhood discovery, cafe/bakery routing, mural/art stops, waterfront paths
- **Intelligence**: Understands "vibe" (historic district vs. industrial vs. waterfront vs. residential)

**Bikepacking & Touring**:
- **Preferences**: Mixed terrain, scenic remote roads, established routes, camping access
- **Avoids**: High-traffic roads, long stretches without services, extremely remote areas without planning
- **Optimization**: Daily distance balance, camping locations, water sources, resupply points
- **Special Features**: Multi-day planning, service point spacing, water source mapping, camping integration
- **Intelligence**: Balances remote adventure with necessary infrastructure access

**Endurance & Training**:
- **Preferences**: Specific elevation profiles, low-traffic roads for intervals, long steady climbs
- **Avoids**: Traffic for high-intensity efforts, frequent stop signs/lights, rough surfaces
- **Optimization**: Training-specific profiles, power zone matching, progressive difficulty
- **Special Features**: Interval segment identification, nutrition stop planning, FTP-based routing
- **Intelligence**: Creates routes matching specific training objectives (threshold, VO2 max, endurance)

**Cross-Discipline Intelligence**:
- Users can switch discipline mid-conversation
- Routes automatically re-optimized for new discipline with appropriate constraints
- AI understands context shifts (e.g., "avoid technical" means different things for road vs. MTB)
- Maintains preference history across all disciplines

**User Stories**:
- As a road cyclist, I get smooth paved routes with good shoulders and minimal traffic
- As a gravel rider, I can specify my desired surface ratio and tire constraints
- As an MTB rider, I get routes on legal trails matching my technical skill level
- As an urban cyclist, I discover interesting neighborhoods via low-stress streets
- As a bikepacker, I plan multi-day routes with proper infrastructure spacing
- As a training cyclist, I find routes matching specific power zone requirements
- As any cyclist, I can easily switch between my bikes and get appropriate routes for each

### 8. User Preferences & Personalization

**Description**: Persistent user preferences that inform route generation and provide personalized recommendations.

**Preference Categories**:

**Fitness & Experience**:
- Bike types owned (road, gravel, MTB, eMTB)
- Fitness level (beginner, intermediate, advanced, expert)
- FTP (Functional Threshold Power) for road/gravel
- Typical riding speed (mph/kph)
- Max comfortable climb (feet/meters)
- MTB skill level (separate from fitness)
- Risk tolerance (low, medium, high)

**Route Preferences**:
- Preferred route type (loops, out-and-back, point-to-point)
- Typical ride duration
- Surface preferences (% sliders for pavement/gravel/singletrack)
- Climb emphasis (-3 to +3, where 3 = seek climbing)
- Scenery importance
- Social vs. solo riding preferences

**Avoidances**:
- Highway/freeway avoidance
- High-traffic roads
- Technical features (exposure, drops, jumps)
- Surface types (mud, loose rocks, sand)
- Hazards (water crossings, wildlife areas)

**Preferences in Use**:
- Pre-fill chat requests ("Plan my usual Saturday ride")
- Route scoring alignment
- Validation thresholds
- Suggested prompt generation

**Preference Learning**:
- AI observes user feedback and adjustments
- "You seem to prefer routes with <10% pavement. Should I remember this?"
- Implicit learning from accepted vs. rejected routes
- Explicit preference updating through chat

**User Stories**:
- As a returning user, the AI knows my fitness level and bike type
- As a user, I can say "my usual loop" and the AI knows what I mean
- As a beginner, I automatically get easier route suggestions
- As a user with fear of heights, routes automatically avoid exposure

---

## User Stories (Comprehensive)

### Route Discovery & Planning

**Epic 1: Initial Route Creation**
- As a user, I can describe my ideal ride in plain English and receive route options
- As a user, I can specify starting location by address, coordinates, or "current location"
- As a user, I can choose route type (loop, out-and-back, point-to-point)
- As a user, I can set distance, time, or "just explore" constraints
- As a user, I receive multiple route options when quality mode is enabled

**Epic 2: Route Refinement**
- As a user, I can ask the AI to "make it harder/easier/longer/shorter"
- As a user, I can request more/less elevation
- As a user, I can change surface type emphasis
- As a user, I can add/remove waypoints through chat or map
- As a user, I can specify areas to avoid
- As a user, I can lock portions of route while editing others

**Epic 3: Route Analysis**
- As a user, I can view detailed elevation profile with grade coloring
- As a user, I can see surface breakdown percentages
- As a user, I can view MTB difficulty distribution
- As a user, I can see estimated time with pace assumptions
- As a user, I can identify steep sections on the profile
- As a user, I can see where technical features occur
- As a user, I can view segment-by-segment details

### AI Interaction

**Epic 4: Natural Conversation**
- As a user, I can use cycling jargon and the AI understands
- As a user, I can refer to previous messages ("make that route longer")
- As a user, I can ask follow-up questions about routes
- As a user, I can request explanations of AI decisions
- As a user, I receive suggested follow-up prompts
- As a user, I can interrupt the AI mid-generation to refine

**Epic 5: AI Transparency**
- As a user, I can see the AI's confidence score on route data
- As a user, I can view which data sources were used
- As a user, I can see why one route was recommended over another
- As a user, I am warned when data is incomplete
- As a user, I can see trade-off explanations for route choices
- As a user, I understand what constraints are hard vs. soft

### Safety & Validation

**Epic 8: Pre-Ride Validation**
- As a user, I am warned about illegal route segments
- As a user, I am alerted to dangerous conditions (exposure, traffic)
- As a user, I receive skill level mismatch warnings
- As a user, I am notified of data gaps and low-confidence areas
- As a user, I can view all validation issues on a list and map
- As a user, I receive actionable fix suggestions

**Epic 9: Emergency & Bail-Out Planning**
- As a user, I can view escape routes from any point (future feature)
- As a user, I can see cell service coverage estimates (future feature)
- As a user, I am shown nearest services (bike shops, hospitals) (future feature)

### Sharing & Export

**Epic 10: Route Sharing**
- As a user, I can export routes to GPX format
- As a user, I can export to TCX with power targets (future feature)
- As a user, I can share routes via link
- As a user, I can send routes to Strava/Garmin/Wahoo (future feature)
- As a user, I can print cue sheets (future feature)

**Epic 11: Social Features**
- As a user, I can make routes public for others to discover (future feature)
- As a user, I can see popular routes in my area (future feature)
- As a user, I can follow other users' route libraries (future feature)
- As a user, I can leave condition reports on routes (future feature)

### Mobile & Field Use

**Epic 12: Mobile Experience**
- As a user on mobile, I can access full chat and map interface
- As a user on mobile, I can use "current location" as starting point
- As a user on mobile, I can view simplified route stats on small screens
- As a user on mobile, I can quickly export to my bike computer (future feature)

**Epic 13: Offline & In-Ride** (future features)
- As a user, I can download routes for offline viewing
- As a user, I can record rides and compare to planned route
- As a user, I can receive turn-by-turn navigation
- As a user, I can see real-time progress on elevation profile

### Personalization

**Epic 14: Preference Management**
- As a user, I can set my fitness level and bike types
- As a user, I can save favorite starting locations
- As a user, I can set default avoidances
- As a user, I can update my skill level as I progress
- As a user, I can save preferred surface ratios
- As a user, I can manage saved avoidance areas

**Epic 15: Route Library**
- As a user, I can save routes to my library
- As a user, I can organize routes into collections (trips, favorites, etc.)
- As a user, I can re-ride previous routes
- As a user, I can see my route history
- As a user, I can compare stats across my rides (future feature)

---

## Technical Architecture

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend Layer                          │
│  ┌────────────────────┐  ┌────────────────────┐                │
│  │   Next.js 14 App   │  │   MapLibre GL JS   │                │
│  │   - Chat UI        │  │   - Route Editing  │                │
│  │   - Controls       │  │   - Map Controls   │                │
│  │   - Inspector      │  │   - Layer Mgmt     │                │
│  └────────────────────┘  └────────────────────┘                │
│  ┌────────────────────────────────────────────┐                │
│  │   Zustand State Management                 │                │
│  │   - chatStore   - routeStore               │                │
│  │   - uiStore     - preferencesStore         │                │
│  │   - preferencesStore                       │                │
│  └────────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ REST API / WebSocket
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend API Layer                          │
│                   FastAPI • Python 3.11 • Async                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    API Endpoints                           │ │
│  │  /api/chat           /api/routes                        │ │
│  │  /api/geocode        /api/users       /api/health         │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Service Layer                           │ │
│  │  • ai_copilot.py     - Claude API integration             │ │
│  │  • routing.py        - OpenRouteService client            │ │
│  │  • analysis.py       - Route analysis engine              │ │
│  │  • validation.py     - Validation rules engine            │ │
│  │  • route_planner.py  - Multi-candidate generation         │ │
│  │  • trail_database.py - Trail data management              │ │
│  │  • elevation.py      - Elevation profile processing       │ │
│  │  • geocoding.py      - Location services                  │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
              │                    │                    │
              ▼                    ▼                    ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│   PostgreSQL     │   │      Redis       │   │  Celery Workers  │
│   + PostGIS      │   │   (Cache/Queue)  │   │  (Async Jobs)    │
│                  │   │                  │   │                  │
│  • Users         │   │  • API Cache     │   │  • Route gen     │
│  • Routes        │   │  • Session Store │   │  • Validation    │
│  • Conversations │   │  • Job Queue     │   │  • Analysis      │
│  • Waypoints     │   └──────────────────┘   └──────────────────┘
│  • Preferences   │
└──────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     External Services                            │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │ OpenRouteService │  │   Anthropic API  │  │  Nominatim    │ │
│  │  (Routing)       │  │   (Claude 3.5)   │  │  (Geocoding)  │ │
│  └──────────────────┘  └──────────────────┘  └───────────────┘ │
│  ┌──────────────────┐  ┌──────────────────┐                    │
│  │  MapTiler API    │  │  Trail Org APIs  │  (Future)          │
│  │  (Map Tiles)     │  │  (Conditions)    │                    │
│  └──────────────────┘  └──────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

### Technology Stack

**Frontend**
- **Framework**: Next.js 14 (React 18)
- **Language**: TypeScript 5.3
- **State Management**: Zustand 4.5 with Immer
- **UI Components**: Material-UI (MUI) 5.15
- **Map Rendering**: MapLibre GL JS 4.0, react-map-gl 7.1
- **Charts**: Recharts 2.12
- **HTTP Client**: Axios 1.6
- **Data Fetching**: TanStack Query 5.18
- **Date Handling**: date-fns 3.3
- **Build Tool**: Next.js built-in (Turbopack)

**Backend**
- **Framework**: FastAPI 0.104+
- **Language**: Python 3.11
- **Async Runtime**: asyncio, httpx
- **Database ORM**: SQLAlchemy 2.0 with async support
- **Migration Tool**: Alembic
- **Validation**: Pydantic 2.5
- **Task Queue**: Celery 5.3
- **AI Integration**: Anthropic SDK (Claude API)
- **HTTP Client**: httpx (async), requests (sync fallback)
- **Web Scraping**: BeautifulSoup4, lxml

**Infrastructure**
- **Database**: PostgreSQL 15 + PostGIS 3.3
- **Cache/Queue**: Redis 7
- **Containerization**: Docker, Docker Compose
- **Web Server**: Uvicorn (ASGI)
- **Reverse Proxy**: (production) Nginx or Traefik

**External APIs**
- **Routing**: OpenRouteService (ORS)
- **AI**: Anthropic Claude API (Sonnet 3.5)
- **Geocoding**: Nominatim (OpenStreetMap)
- **Map Tiles**: MapTiler, Mapbox (optional)
- **Elevation**: ORS elevation endpoint

### Data Models (Simplified)

**User**
```python
- id: UUID
- email: String
- name: String
- preferences: JSONB (fitness, bikes, preferences)
- created_at: DateTime
- updated_at: DateTime
```

**Route**
```python
- id: UUID
- user_id: UUID (FK)
- name: String
- description: Text
- sport_type: Enum
- geometry: Geometry(LineString) [PostGIS]
- distance_meters: Float
- elevation_gain_meters: Float
- surface_breakdown: JSONB
- mtb_difficulty_breakdown: JSONB
- validation_status: Enum
- validation_results: JSONB
- confidence_score: Float
- tags: Array[String]
- is_public: Boolean
- created_at: DateTime
- updated_at: DateTime
```

**Waypoint**
```python
- id: UUID
- route_id: UUID (FK)
- idx: Integer (order)
- waypoint_type: Enum
- point: Geometry(Point) [PostGIS]
- name: String
- lock_strength: Enum
```

**Conversation**
```python
- id: UUID
- user_id: UUID (FK)
- messages: JSONB (array of message objects)
- context: JSONB (state, preferences)
- created_at: DateTime
- updated_at: DateTime
```

### API Design Principles

**RESTful Endpoints**
- Resources: `/api/{resource}` (e.g., `/api/routes`)
- Actions: POST for creates/actions, GET for reads, PUT/PATCH for updates
- Consistent response format: `{ data, meta, errors }`

**Error Handling**
- HTTP status codes: 200 OK, 201 Created, 400 Bad Request, 401 Unauthorized, 404 Not Found, 500 Server Error
- Error response format: `{ error: { code, message, details } }`

**Versioning**
- API version in header: `Accept: application/vnd.johnrouter.v1+json`
- URL versioning for major changes: `/api/v2/routes` (future)

**Rate Limiting**
- Per-user limits: 100 req/min for general APIs
- AI chat: 20 req/min
- Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

**Authentication** (future)
- JWT tokens for user sessions
- API keys for programmatic access
- OAuth2 for third-party integrations

---

## Product Roadmap

### Phase 1: MVP (Current) - ✅ COMPLETE

**Goal**: Prove core value proposition with early adopters

**Features**:
- ✅ Chat-based route generation
- ✅ OpenRouteService integration
- ✅ Basic route analysis (elevation, distance, time)
- ✅ MTB difficulty mapping (mtb:scale)
- ✅ Surface breakdown analysis
- ✅ Map-based route editing
- ✅ Waypoint management
- ✅ Quality mode (multi-candidate generation)
- ✅ Route validation (connectivity, legality, safety)
- ✅ Export to GPX
- ✅ Multi-sport routing profiles
- ✅ Mobile-responsive UI

**Success Metrics**:
- 50+ beta users
- 500+ routes generated
- 70%+ user satisfaction (survey)
- <5s average route generation time
- 90%+ route validation accuracy

**Timeline**: Q1 2025 (✅ Completed)

---

### Phase 2: Polish & Scale - 🚧 IN PROGRESS

**Goal**: Production-ready quality, performance optimization

**Features**:
- ⏳ User authentication and accounts
- ⏳ Personal route library
- ⏳ Route sharing (public/private)
- ⏳ Advanced route editing (segment operations, split/merge)
- ⏳ Improved AI copilot (better tool calling, streaming)
- ⏳ Performance improvements (sub-3s route generation)
- ⏳ Database optimization (spatial indexing)
- ⏳ Error handling and recovery
- ⏳ Analytics and monitoring (Sentry, Mixpanel)

**Infrastructure**:
- Production deployment (AWS/GCP/Railway)
- CI/CD pipeline (GitHub Actions)
- Automated testing (80%+ coverage)
- Database backups and disaster recovery
- CDN for static assets

**Success Metrics**:
- 500+ active users
- 5,000+ routes created
- <3s p95 route generation
- 99.5% uptime
- 85%+ user retention (30-day)

**Timeline**: Q2 2025

---

### Phase 3: Enhanced Intelligence - 📅 PLANNED

**Goal**: Industry-leading AI capabilities and data quality

**Features**:
- 🔮 Preference learning (implicit from user behavior)
- 🔮 "My usual ride" recognition
- 🔮 Seasonal route recommendations
- 🔮 Weather-aware routing (mud avoidance, heat adaptation)
- 🔮 Trail organization API integrations (Trailforks, MTB Project)
- 🔮 Community condition reports
- 🔮 Photo integration (route highlights)
- 🔮 Strava heatmap integration (popularity routing)
- 🔮 Predictive closure detection (fire season, snow)

**AI Improvements**:
- Route memory and learning ("similar to your Boulder loop")
- Explainable AI dashboard (why this route?)
- Conversational route comparison

**Success Metrics**:
- 2,000+ active users
- 20,000+ routes created
- 4.5+ star average rating

**Timeline**: Q3 2025

---

### Phase 4: Social & Community - 📅 PLANNED

**Goal**: Build network effects and user-generated content

**Features**:
- 🔮 Public route discovery feed
- 🔮 User profiles and following
- 🔮 Route collections (curated lists)
- 🔮 Social features (likes, comments, saves)
- 🔮 Group ride planning
- 🔮 Event route builder (race directors)
- 🔮 Route verification badges (ridden, verified)
- 🔮 Leaderboards and challenges
- 🔮 Route recommendations engine
- 🔮 Popular routes in your area

**Community Tools**:
- Trail condition reporting
- Photo uploads with route location
- Route rating and reviews
- Ambassador program (local experts)

**Success Metrics**:
- 5,000+ active users
- 50,000+ total routes
- 30%+ routes shared publicly
- 10%+ users contributing condition reports

**Timeline**: Q4 2025

---

### Phase 5: Advanced Features - 📅 FUTURE

**Goal**: Premium features and advanced use cases

**Features**:
- 🔮 Multi-day tour planning
- 🔮 Bikepacking route builder (camping, water, resupply)
- 🔮 Training plan integration (structured workouts)
- 🔮 Power-based route planning (FTP zones)
- 🔮 Real-time navigation (turn-by-turn)
- 🔮 Offline maps and routes
- 🔮 Live tracking and safety features
- 🔮 Integration with bike computers (Garmin, Wahoo, Hammerhead)
- 🔮 Route matching (find similar routes elsewhere)
- 🔮 Historical weather data routing

**Advanced Analysis**:
- Fatigue modeling (route gets harder as you tire)
- Nutrition and hydration planning
- Thermal comfort routing (shade seeking)
- Wind-aware routing
- Surface quality scoring beyond binary (roughness index)

**Monetization**:
- Premium tier: Advanced features
- API access for partners (bike shops, tourism boards)
- White-label solutions for trail organizations
- B2B licensing for cycling apps

**Timeline**: 2026+

---

## Success Metrics & KPIs

### North Star Metric
**Routes Generated per Week with High Satisfaction**
- Combines engagement (routes created) with quality (user satisfaction >4/5 stars)

### Product Metrics

**Engagement**
- Daily Active Users (DAU) / Monthly Active Users (MAU)
- Routes generated per user per month
- Chat messages sent per session
- Time spent in app per session
- Return rate (7-day, 30-day)

**Quality**
- Route validation pass rate (target: >95%)
- AI decision confidence score (avg, target: >0.8)
- User rating of generated routes (target: >4.2/5)

**Performance**
- Route generation time p50, p95 (target: <3s, <8s)
- AI response time (target: <2s first token)
- Frontend load time (target: <1.5s)

**Conversion & Retention**
- New user activation (generate first route) (target: >80%)
- 7-day retention (target: >40%)
- 30-day retention (target: >25%)
- Power user conversion (>10 routes) (target: >15%)

**Safety & Trust**
- Validation issue detection rate
- User-reported route problems (target: <2%)
- Data incident reports (target: 0)

### Business Metrics (Future)

**Acquisition**
- Organic traffic (SEO)
- Referral rate (users inviting others)
- Social media engagement
- Partnership referrals

**Revenue** (when monetization launches)
- Monthly Recurring Revenue (MRR)
- Customer Lifetime Value (LTV)
- Premium conversion rate
- Churn rate

**Cost**
- Cost per route (API costs)
- Infrastructure cost per user
- Customer Acquisition Cost (CAC)
- LTV:CAC ratio

---

## Competitive Analysis

### Direct Competitors

#### Komoot
**Strengths**:
- Large user base (25M+ users)
- Extensive offline maps
- Good community features
- Multi-sport support

**Weaknesses**:
- Poor MTB difficulty ratings
- No AI assistance
- Limited route refinement
- Opaque routing decisions
- Weak condition information

**Differentiation**: John Router's AI copilot and comprehensive multi-discipline intelligence provide superior experience for all cyclists, not just one type.

#### Strava Routes
**Strengths**:
- Massive user base (100M+)
- Heatmap-based routing (popular routes)
- Integrated with Strava ecosystem
- Simple interface

**Weaknesses**:
- No difficulty or surface analysis
- No AI assistance
- Very basic route editing
- No validation
- Road-cycling focused

**Differentiation**: John Router provides deep, discipline-specific intelligence for all cycling styles with AI-powered planning that Strava lacks entirely.

#### RideWithGPS
**Strengths**:
- Powerful route editor
- Excellent data analysis
- Strong navigation features
- Good cue sheets

**Weaknesses**:
- No AI assistance
- Dated UI/UX
- Manual waypoint placement required
- Complex for beginners

**Differentiation**: John Router's conversational interface makes world-class routing accessible to novices while maintaining pro features.

#### Trailforks
**Strengths**:
- Best MTB trail database
- Crowd-sourced conditions
- Excellent trail details
- Strong community

**Weaknesses**:
- Trail database only (no road/gravel)
- Limited route planning features
- No AI assistance
- Requires manual trail selection
- Coverage gaps outside major MTB areas

**Differentiation**: John Router brings Trailforks-level depth to ALL cycling disciplines (not just MTB) with AI-powered conversational planning.

### Indirect Competitors

- **Google Maps / Apple Maps**: General navigation, not cycling-specific
- **AllTrails**: Hiking-focused, poor for cycling
- **Gaia GPS**: Strong for backcountry but not cycling-optimized
- **Outdooractive**: European focus, similar to Komoot

### Competitive Advantages

1. **AI-First Design**: Only cycling route planner with truly conversational AI that understands context and nuance
2. **Multi-Discipline Excellence**: Industry-leading depth across ALL cycling disciplines—MTB, road, gravel, urban, bikepacking, endurance
3. **Transparent Decisions**: Explain mode, confidence scores, data transparency—you always understand why
4. **Quality Mode**: Multi-candidate generation with comprehensive validation unique in market
5. **Professional + Accessible**: Power features without complexity—beginners can chat, experts can fine-tune
6. **Celebration of Diversity**: Recognizes that cycling is deeply personal; no discipline privileged over another

---

## Design Principles

### 1. Quality Over Speed
**Never sacrifice accuracy for speed.** It's better to take 10 seconds and generate a safe, validated route than return a dangerous route in 2 seconds.

**Implementation**:
- Quality mode enabled by default
- Always run validation checks
- Show confidence scores
- Warn users about data gaps

### 2. Transparency Over Magic
**Explain AI decisions, don't hide them.** Users should understand why routes were chosen and feel in control.

**Implementation**:
- Explain mode shows reasoning
- Confidence scores on all derived data
- Citation of sources
- Trade-off explanations
- Allow manual override of any AI decision

### 3. Every Cycling Discipline Deserves Excellence
**No discipline is an afterthought—all cycling is personal and valid.** Whether you seek technical singletrack, smooth pavement, quiet neighborhoods, or remote gravel roads, your preferences matter equally and deserve the same depth of analysis.

**Implementation**:
- MTB: Trail difficulty ratings (mtb:scale), technical features, flow analysis
- Road: Traffic levels, bike infrastructure, pavement quality, climb categorization
- Gravel: Surface composition, quality assessment, tire suitability
- Urban: Neighborhood character, stress levels, point-of-interest integration
- Bikepacking: Infrastructure spacing, camping/water access, multi-day logistics
- All disciplines receive equal investment in data quality and routing intelligence

### 4. Progressive Disclosure
**Simple by default, powerful when needed.** Novices get approachable UI, experts get professional tools.

**Implementation**:
- Chat interface for beginners
- Advanced controls collapsible/hidden
- Smart defaults based on user preferences
- Gradual feature introduction
- Context-sensitive help

### 5. Data Integrity
**Treat user safety as paramount.** Better to say "I don't know" than to guess incorrectly.

**Implementation**:
- Distinguish OSM data from estimates
- Show data completeness scores
- Validate all routes before presenting
- Surface validation errors prominently

### 6. Fail Gracefully
**When things go wrong, fail informatively.** Help users understand what happened and what to do next.

**Implementation**:
- Clear error messages
- Actionable fix suggestions
- Rollback on failed operations
- Retry with exponential backoff
- Graceful degradation (when ORS down, use alternatives)

---

## Use Cases & Scenarios

### Use Case 1: Local Exploration
**Actor**: Weekend Warrior Jessica
**Goal**: Find a new beginner-friendly MTB trail near Austin

**Flow**:
1. Jessica opens John Router on her phone
2. Says: "Find me an easy 1-hour mountain bike ride near Austin"
3. AI generates 3 loop options, all green/blue trails
4. Jessica views routes on map, sees one near a trailhead she knows
5. Clicks route to see details: 8 miles, 600ft climbing, 90% singletrack
6. Elevation profile shows gradual climbs, no steep sections
7. Validation shows all-green (no issues)
8. Jessica exports to GPX, loads on her phone, rides it this weekend
9. Returns to app, saved to favorites

**Success**: Jessica found a perfect beginner trail without trial-and-error.

---

### Use Case 2: Destination Trip Planning
**Actor**: Destination Planner David
**Goal**: Plan 3 days of riding in Moab before his trip

**Flow**:
1. David opens laptop, says: "I'm going to Moab for 3 days, what are the must-ride trails?"
2. AI responds with list: Slickrock Trail, Magnificent 7, Porcupine Rim, Captain Ahab
3. David: "Create routes for each, intermediate to advanced difficulty"
4. AI generates 4 routes, shows side-by-side comparison
5. David reviews: Slickrock (12mi, very hard), Mag 7 (17mi, hard), Porcupine (13mi, hard + exposure), Ahab (16mi, hard)
6. David: "Porcupine has exposure warnings, what does that mean?"
7. AI explains: cliff edges, recommends if comfortable with heights
8. David decides to skip Porcupine, saves other 3
9. David exports all routes, loads on Garmin, confident he has great rides planned

**Success**: David planned 3 days in under 30 minutes with high confidence.

---

### Use Case 3: Iterative Refinement
**Actor**: Technical Trail Seeker Sarah
**Goal**: Create a custom 2-hour loop from home with specific characteristics

**Flow**:
1. Sarah: "Create a 2-hour MTB loop from my house in Boulder"
2. AI generates loop: 15 miles, 2,000ft, 60% singletrack
3. Sarah reviews route, notices it includes paved section she dislikes
4. Sarah: "Avoid pavement on 28th Street, use trails instead"
5. AI re-routes through Marshall Mesa trails, now 80% singletrack
6. Sarah checks elevation: sees 15% grade section
7. Sarah: "Too steep, make it less chunky"
8. AI finds alternative route avoiding steepest climb, now 10% max grade
9. Sarah reviews difficulty: 40% blue, 60% black
10. Sarah: "Perfect! Add a coffee stop at Ozo on the way back"
11. AI adjusts route to pass Ozo Coffee, adds waypoint
12. Sarah locks the coffee shop waypoint, drags route slightly to include favorite overlook
13. Final route: 16 miles, 1,800ft, 80% singletrack, coffee stop, overlook, perfect difficulty
14. Saves as "Saturday Shred Loop"

**Success**: Sarah created a custom route through iterative conversation + manual editing.

---

### Use Case 4: Gravel Adventure Discovery
**Actor**: Gravel Explorer Marcus
**Goal**: Find a 50-mile scenic gravel loop in Oregon

**Flow**:
1. Marcus: "Plan a 50-mile gravel loop from Portland with great views and minimal pavement"
2. AI generates 3 candidates:
   - Route A: 48mi, 3,200ft, 15% pavement, Mt. Hood views
   - Route B: 52mi, 2,400ft, 8% pavement, Columbia Gorge views
   - Route C: 51mi, 4,000ft, 5% pavement, mountain route, very scenic
3. AI recommends Route C: "Most scenic, best gravel quality, but significant climbing"
4. Marcus compares elevation profiles, Route C has challenging climbs but great descents
5. Marcus checks surface breakdown: 75% gravel, 20% dirt, 5% pavement
6. Marcus: "Will this be rideable on 38mm tires?"
7. AI analyzes surface: "Yes, gravel is mostly compacted. One 2-mile dirt section may be loose."
8. Marcus selects Route C, adjusts one waypoint to include viewpoint
11. Adds water refill waypoint at mile 30 (small town)
12. Exports to GPX with water/coffee stops marked

**Success**: Marcus found an epic gravel adventure with confidence in rideability and conditions.

---

### Use Case 5: Group Ride Planning
**Actor**: Cycling Coach
**Goal**: Create a gravel route for mixed-ability group ride

**Flow**:
1. Coach: "Create a 30-mile gravel route for a group with fitness levels from beginner to advanced, starting from Bentonville"
2. AI generates loop: 28 miles, 1,500ft, 70% gravel, moderate difficulty
3. Coach reviews, notices one 12% grade climb
4. Coach: "That climb will drop our beginner riders. Find an easier option."
5. AI re-routes avoiding steep climbs, now 8% max grade, slightly longer route
6. Coach adds coffee shop stop at mile 15 (regroup point)
7. Coach locks first 10 miles (warm-up section he knows is perfect)
8. Drags route to include specific scenic overlook
9. Adds bailout waypoint at mile 20 (shortcut back for struggling riders)
10. Reviews surface: 65% gravel, 30% pavement, 5% dirt - good for variety
11. Exports to GPX, shares route link with group
12. Participants can view route, elevation, surface breakdown before ride

**Success**: Coach created inclusive route with bailout options and clear regroup points.

---

### Use Case 6: Urban Neighborhood Discovery
**Actor**: Urban Rambler Chen
**Goal**: Explore new Brooklyn neighborhoods on a Sunday morning

**Flow**:
1. Chen: "Plan a 15-mile leisurely ride through interesting Brooklyn neighborhoods, mostly quiet streets"
2. AI generates 3 loop options emphasizing low-stress streets and interesting areas
3. Chen reviews routes, sees one connects Prospect Park, Greenwood Cemetery, and Red Hook
4. Clicks route: 14.5 miles, minimal elevation, 80% residential streets, 15% bike lanes, 5% greenway
5. Route analysis shows stress levels: 90% low-stress, 10% moderate (with bike lanes)
6. Chen: "Add a bakery stop in Park Slope and avoid the Gowanus"
7. AI adjusts route to include popular bakery, reroutes around Gowanus industrial area
8. Chen reviews POIs along route: 3 cafes, 2 parks, historic cemetery, waterfront views
9. Validation shows safe crossings, good lighting, no dangerous intersections
10. Chen: "Perfect! Make it a little shorter, maybe 12 miles"
11. AI shortens route by removing Red Hook segment, keeps Park Slope and Greenwood
12. Final route: 12.2 miles, quiet streets, bakery stop, cemetery loop, scenic neighborhoods
13. Chen exports and rides, discovers new favorite streets

**Success**: Chen explored new neighborhoods safely and leisurely, found hidden gems, avoided stress.

---

### Use Case 7: Road Training with Specific Objectives
**Actor**: Road Training Enthusiast Priya
**Goal**: Create a century training ride with specific climbing for upcoming event

**Flow**:
1. Priya: "Plan a 100-mile training ride from Austin with 5,000ft of climbing, mostly on quiet roads"
2. AI generates route: 98 miles, 5,200ft, 85% low-traffic roads
3. Priya reviews elevation profile: several moderate climbs, one long sustained climb
4. Priya checks traffic analysis: 15% on busier roads with good shoulders
5. Priya: "Can you make the climbing more evenly distributed? And add a coffee stop at mile 50"
6. AI regenerates: climbs now spread throughout, coffee shop in Dripping Springs at mile 52
7. Priya reviews climb categorization: 2 Cat 4 climbs, 3 Cat 3 climbs, 1 Cat 2 climb
8. Priya: "Perfect climb distribution. Can you add a bailout option at mile 70?"
9. AI identifies shortcut back to Austin from mile 70 (saves 25 miles)
10. Priya checks pavement quality: 90% good to excellent, 10% fair (rural roads)
11. Validation shows: all roads bike-legal, good shoulders on busier sections
12. Priya adds water refill points at miles 30, 50, and 75
13. Exports to TCX with lap markers at each climb for bike computer

**Success**: Priya created perfect training ride matching event profile with proper nutrition/bailout planning.

---

## Risk Assessment & Mitigation

### Technical Risks

**Risk 1: OpenRouteService Downtime**
- **Impact**: High - core routing unavailable
- **Probability**: Medium (external dependency)
- **Mitigation**:
  - Implement retry with exponential backoff
  - Cache recent routing requests (24hr TTL)
  - Add fallback routing service (GraphHopper, Valhalla)
  - Display clear error message with estimated recovery time

**Risk 2: Claude API Rate Limits**
- **Impact**: High - chat interface degraded
- **Probability**: Medium (usage spikes)
- **Mitigation**:
  - Implement request queuing
  - Per-user rate limiting
  - Upgrade to higher tier Claude API access
  - Offer "fast mode" with simpler prompts for rate-limited users

**Risk 3: Poor Route Quality from AI**
- **Impact**: High - user safety, trust
- **Probability**: Medium (edge cases)
- **Mitigation**:
  - Always run validation before showing routes
  - Quality mode generates multiple candidates
  - Manual override always available
  - User feedback loop to identify problematic patterns
  - Comprehensive validation testing

**Risk 4: Database Performance at Scale**
- **Impact**: Medium - slow queries affect UX
- **Probability**: High (growth)
- **Mitigation**:
  - PostGIS spatial indexing
  - Query optimization and EXPLAIN analysis
  - Read replicas for heavy queries
  - Aggressive caching with Redis
  - Database connection pooling

### Business Risks

**Risk 6: Competition from Established Players**
- **Impact**: High - market share threat
- **Probability**: Medium
- **Mitigation**:
  - Differentiate through AI-first conversational design (significant moat)
  - Excel across ALL cycling disciplines rather than specializing in one
  - Build diverse community and network effects quickly across all cycling types
  - Patent novel AI routing techniques
  - Partnerships across all cycling contexts (trail orgs, clubs, shops, advocacy groups)

**Risk 7: API Cost Scaling**
- **Impact**: Medium - unit economics
- **Probability**: High (growth)
- **Mitigation**:
  - Cache aggressively (80%+ cache hit rate target)
  - Optimize AI prompts for token efficiency
  - Tiered pricing for power users
  - Bulk API pricing negotiations
  - Self-hosted routing engine (long-term)

**Risk 8: User Safety Incidents**
- **Impact**: Critical - liability, reputation
- **Probability**: Low but possible
- **Mitigation**:
  - Prominent disclaimers (always verify conditions)
  - Comprehensive validation and warnings
  - User responsibility acknowledgment
  - Insurance coverage
  - Clear ToS limiting liability
  - Safety-first culture in product decisions

### Operational Risks

**Risk 9: Data Quality Issues**
- **Impact**: Medium - poor UX, trust damage
- **Probability**: High (OSM data varies)
- **Mitigation**:
  - Show confidence scores always
  - Distinguish verified data from estimates
  - User-reported corrections
  - Data quality monitoring and alerts
  - OSM contribution program (improve source data)

**Risk 10: Scaling Team & Support**
- **Impact**: Medium - can't keep up with growth
- **Probability**: High (if successful)
- **Mitigation**:
  - Comprehensive in-app help and docs
  - AI-powered support chatbot
  - Community forum for peer support
  - Clear escalation paths
  - Proactive monitoring and error detection

---

## Go-to-Market Strategy

### Target Launch Markets (Prioritized)

1. **Colorado (Denver/Boulder)**: Dense MTB/road/gravel community, tech-savvy users, year-round riding, diverse terrain
2. **Pacific Northwest (Portland/Seattle)**: Strong gravel culture, urban cycling infrastructure, high cycling participation across disciplines
3. **California (Bay Area, SoCal)**: Large diverse cycling population, road racing heritage, growing gravel scene, urban cycling
4. **New York Metro**: Massive urban cycling community, growing interest in gravel/adventure, strong group ride culture
5. **North Carolina (Pisgah/Asheville)**: Destination MTB, Blue Ridge Parkway road cycling, gravel growth, strong advocacy
6. **Texas (Austin, DFW, Houston)**: Growing cycling scenes across all disciplines, year-round riding, strong community
7. **Utah (Moab/Salt Lake)**: Destination riding for all disciplines, trip planning needs

### Marketing Channels

**Phase 1: Early Adopter Acquisition**
- Reddit (r/MTB, r/gravelcycling, r/bicycling, r/bikecommuting, r/randonneuring, r/bikepacking)
- Cycling forums (MTBR, Pinkbike, WeightWeenies, BikeForums, Paceline)
- Local cycling clubs and Facebook groups (road, MTB, gravel, urban)
- YouTube cycling channel partnerships (across all disciplines)
- Cycling podcast sponsorships (The Gravel Ride, Nerd Alert, etc.)
- In-person demos at events, shops, group rides, trailheads

**Phase 2: Organic Growth**
- SEO (trail guides, road route planning, urban cycling, bikepacking routes)
- Content marketing ("How to plan the perfect [MTB/road/gravel/urban] ride")
- User-generated content (shared routes across all disciplines)
- Referral program (invite friends)
- Integration with Strava/Ride with GPS (share routes)
- Partnerships: trail orgs, cycling clubs, advocacy groups, tourism boards

**Phase 3: Paid Acquisition**
- Instagram/Facebook ads (cycling communities)
- Google Search ads (high-intent keywords)
- YouTube pre-roll (cycling videos)
- Influencer partnerships
- Event sponsorships (gravel races, MTB festivals)

### Partnership Strategy

**Trail Organizations**
- Co-marketing: Featured route collections
- Revenue share: Premium tier with trail org features
- Examples: IMBA chapters, local trail alliances

**Bike Shops**
- In-store demos and recommendations
- Custom route creation for customers
- "Recommended by [Shop Name]" badge
- Revenue share on premium conversions

**Tourism Boards**
- Destination route collections
- "Official route guide" partnerships
- Co-marketing campaigns
- White-label solutions for regional sites

**Cycling Events**
- Route planning tools for organizers
- Official race route builder partnership
- Event-specific route discovery
- Participant route sharing

### Pricing Strategy (Future)

**Free Tier**:
- Unlimited route generation
- Basic analysis and validation
- 5 saved routes
- GPX export

**Premium Tier** ($9.99/month or $99/year):
- Unlimited saved routes
- Advanced features (multi-day planning, training plans)
- Priority AI (faster, higher limits)
- Offline maps
- Integration with bike computers
- Early access to new features

**Pro Tier** ($29.99/month) (for coaches, guides, organizers):
- All Premium features
- Group ride planning tools
- Route collections (curated, published)
- Client management (for coaches)
- White-label options
- API access
- Priority support

---

## Appendix

### Glossary

- **mtb:scale**: OpenStreetMap tag (0-6) indicating mountain bike trail difficulty
- **Surface Breakdown**: Percentage distribution of route across surface types (pavement, gravel, dirt, singletrack)
- **Quality Mode**: Multi-candidate route generation with comprehensive validation
- **Waypoint**: Defined point on route (start, end, via, POI)
- **Hard Lock**: Waypoint that cannot be moved by AI re-routing
- **Soft Lock**: Waypoint that AI can adjust slightly (<100m) for optimization
- **Avoidance Area**: Polygon region to exclude from routing
- **Validation Issue**: Route problem identified by validation service
- **Confidence Score**: 0-1 metric indicating data quality certainty
- **Hike-a-Bike**: Trail segment too steep/technical to ride
- **Exposure**: Trail segment with dangerous drop-offs or cliff edges
- **Technical Features**: MTB obstacles (rocks, roots, drops, jumps)
- **Route Type**: Loop (same start/end), Out-and-Back, or Point-to-Point
- **Sport Type**: Road, Gravel, MTB, eMTB, Urban, Bikepacking routing profile
- **Traffic Stress**: Level of vehicular traffic exposure and safety concern
- **Bike Infrastructure**: Dedicated cycling facilities (protected lanes, bike lanes, sharrows, cycletracks)
- **Pavement Quality**: Road surface condition assessment
- **Neighborhood Character**: Urban area classification (residential, commercial, industrial, parkway, waterfront)
- **Climb Categorization**: Road cycling hill classification (Cat 4, 3, 2, 1, HC based on length and gradient)

### Technical Glossary

- **ORS**: OpenRouteService, routing API
- **PostGIS**: PostgreSQL extension for spatial/geographic data
- **GeoJSON**: JSON format for encoding geographic data structures
- **LineString**: GeoJSON geometry type representing a route (sequence of coordinates)
- **Zustand**: React state management library
- **FastAPI**: Modern Python web framework
- **Celery**: Distributed task queue for Python
- **MapLibre**: Open-source map rendering library
- **Async/Await**: Python asynchronous programming pattern
- **Pydantic**: Python data validation library
- **SQLAlchemy**: Python SQL toolkit and ORM

---

## Document Metadata

- **Version**: 1.1
- **Last Updated**: January 21, 2026
- **Author**: Product Team
- **Status**: Living Document
- **Next Review**: March 2026
- **Major Revision**: Repositioned to celebrate all cycling disciplines equally

---

## Changelog

- **v1.1** (Jan 21, 2026): Major revision to celebrate cycling diversity
  - Repositioned from "MTB-first" to "every cycling discipline matters equally"
  - Added 3 new user personas (Urban Rambler, Road Training Enthusiast, Bikepacking Adventurer)
  - Expanded "MTB-First Route Analysis" to "Comprehensive Cycling Intelligence" with equal coverage of road, gravel, MTB, urban, bikepacking, and endurance cycling
  - Rewrote design principle #3 to "Every Cycling Discipline Deserves Excellence"
  - Expanded multi-sport section to "Multi-Discipline Routing Intelligence" with deep detail for all cycling types
  - Added 2 new use cases (Urban Neighborhood Discovery, Road Training with Specific Objectives)
  - Updated competitive positioning to emphasize breadth across all cycling, not just off-road
  - Expanded target markets and marketing channels to reflect diverse cycling communities
  - Updated executive summary and mission to honor the personal and diverse nature of cycling

- **v1.0** (Jan 21, 2026): Initial comprehensive product documentation created
