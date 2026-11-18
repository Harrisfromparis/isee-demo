/*
 * ISEE — settings for the Eircode and address search ("see it from the street").
 * © 2026 Elaine Walsh, Autism & Me. All rights reserved.
 *
 * This is the only file you need to edit. See street/README.md for the steps.
 */
window.ISEE_STREET = {
  /*
   * Your Google Maps key goes between the quotes.
   * Leave it empty and the search still works, but the map and street view
   * open in Google Maps in a new tab instead of inside ISEE.
   * Lock the key to your own websites before you paste it here (README, step 4).
   */
  googleMapsKey: "",

  /* Searches lean towards places in Ireland. */
  region: "IE",

  /* How close (in metres) a searched address must be to a venue to count as that venue. */
  matchRadiusMetres: 60,

  /*
   * Real venues that have published an ISEE guide. The door opens only for these.
   * The demonstration has none, because every demonstration venue is made up.
   *
   * Example of one entry (remove the two slashes to use it):
   * { slug: "my-venue", name: "My Venue", eircode: "X91 AB12", lat: 52.2593, lng: -7.1101,
   *   door: "/venues/my-venue/preview" },
   */
  venues: [],

  /*
   * Made-up venues, so the whole journey can be shown without a real building.
   * These show a drawing, never Google, and nothing is sent anywhere.
   */
  samples: [
    {
      slug: "sample-health-centre",
      name: "Sample Health Centre (fictional)",
      doorLabel: "Accessible entrance (side)",
      door: "/venues/sample-health-centre/preview?from=shc-n-side-ent&to=shc-n-reception&step=1"
    },
    {
      slug: "sample-chapel-and-hall",
      name: "Sample Chapel and Hall (fictional)",
      doorLabel: "Chapel entrance",
      door: "/venues/sample-chapel-and-hall/preview?from=ch-n-chapel-ent&to=ch-n-pews&step=1"
    },
    {
      slug: "sample-picture-house",
      name: "Sample Picture House (fictional)",
      doorLabel: "Entrance",
      door: "/venues/sample-picture-house/preview?from=ph-n-ent&to=ph-n-tickets&step=1"
    }
  ]
};
