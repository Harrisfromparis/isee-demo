# ISEE interactive demonstration

ISEE — Preview before you visit. An Autism & Me service.

This is a demonstration that runs entirely in the browser. The venues are made up. Nothing you enter is
sent anywhere. It is not the hosted ISEE service.

## Copyright

© 2026 Elaine Walsh, Autism & Me. All rights reserved.

This repository is public so that the demonstration can be viewed. It is **not** open source. No licence
is granted to copy, modify, reuse or redistribute any part of it. See [LICENSE](LICENSE).

Open-source components and fonts used inside the page remain under their own licences. See
[THIRD-PARTY.txt](THIRD-PARTY.txt).

Contact: contactautismandme@gmail.com

## Seat finder

`seat-finder/` is a static build of the iSEE beacon-free seat finder (made-up demo venue only).
It is served at https://harrisfromparis.github.io/isee-demo/seat-finder/ . The root `404.html` belongs to it.

## Places directory

`seat-finder/data/` holds a browsable directory of places in each of the 26 counties of the Republic of
Ireland, grouped by county and category (health, schools, places of worship, libraries, cafés, shops and so
on). It is built automatically by `.github/workflows/build-directory.yml` (weekly, and when
`tools/directory/` changes) using `tools/directory/build_directory.py`. Each run writes a plain-text
`summary.txt` next to the data.

**Source and licence:** © OpenStreetMap contributors. Data available under the
[Open Database Licence](https://opendatacommons.org/licenses/odbl/) (ODbL). The directory is a derived
database built only from OpenStreetMap; the extract comes from Geofabrik.

**Eircodes** appear only where the open data already has a correctly formatted `addr:postcode`. They are never
looked up, derived or guessed, so most places have none. No phone numbers, email addresses, websites or
opening hours are included.

**Corrections or removal:** the data is only as good as OpenStreetMap. To correct or remove a place, edit it
at https://www.openstreetmap.org (the change appears here after the next weekly build), or contact Autism &
Me at contactautismandme@gmail.com.
