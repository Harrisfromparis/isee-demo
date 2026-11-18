# Eircode and address search ("see it from the street")

© 2026 Elaine Walsh, Autism & Me. All rights reserved.

This folder adds one thing to the ISEE demonstration: on **Find a venue**, a visitor can type an
Eircode or a street address and see a window with a **map** and a **front view** of the building.
Where the place has a published ISEE guide, **Open the door** hands over to ISEE.

| File | What it is |
|---|---|
| `street-config.js` | The only file you edit: the Google Maps key and the list of real venues. |
| `street.js` | The feature. |
| `street.css` | Its styles. It uses the ISEE colours and fonts already on the page. |

`index.html` loads these three files with one line near the top and two lines at the very bottom.
If `index.html` is ever rebuilt from the full ISEE source, those three lines must be put back, or the
feature should be moved into the full source.

## What works without a Google key

- The search box, its privacy note and its error message.
- The three made-up venues: a drawing of a map and a building front, **Open the door**, and ISEE takes over.
- A real address: the window opens and offers "Open this address in Google Maps" in a new tab.

## Switching on the map and street view

You need a Google Maps key. Google asks for a payment card when you set up billing. Each month has a
free allowance for each service; the current figures are on Google's pricing page:
https://developers.google.com/maps/billing-and-pricing/pricing

1. Go to https://console.cloud.google.com and create a project (for example "ISEE").
2. Set up billing for the project when Google asks.
3. Under **APIs and services**, enable these two: **Maps JavaScript API** and **Geocoding API**.
4. Under **Credentials**, create an **API key**, then restrict it:
   - **Website restriction**: allow only your own addresses, for example
     `https://harrisfromparis.github.io/isee-demo/*` and `https://www.autismandme.ie/*`.
     (If ISEE is shown on your Wix site inside a frame, the address that counts is the one the ISEE page itself is served from.)
   - **API restriction**: allow only Maps JavaScript API and Geocoding API.
5. Under **Quotas**, set a daily limit on each service that keeps you inside the free allowance, and set a budget alert.
6. Open `street-config.js` and paste the key between the quotes after `googleMapsKey:`. Save and publish.

The key is visible to anyone who views the page. That is normal for a Google Maps website key, and it
is why steps 4 and 5 matter: a restricted key only works on your websites. GitHub or Google may email
you to say a key was found in a public repository; with the restrictions in place that is expected.

## Adding a real venue

When a real venue has a published ISEE guide, add it to `venues` in `street-config.js` with its
Eircode and its map position. The door opens only for places in that list. For every other address
ISEE says "No ISEE guide for this place yet". It never guesses what is inside a building.

## Privacy

- Nothing loads from Google, and nothing is sent to Google, until the visitor presses
  **Show the map and front view**. The note beside the button says so.
- ISEE does not store what is typed.
- The made-up venues never use Google.
- The Privacy page gains one sentence describing this exception. The same sentence, and a legal
  check of it, are needed in the full ISEE source before the real service uses this feature.

## Not yet tested against live Google

The Google part was tested with a stand-in for Google's service, because there is no key yet.
After the key is added, check one Eircode, one street address, one nonsense entry, and one rural
address with no street view.
