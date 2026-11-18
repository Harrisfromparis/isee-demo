/*
 * ISEE — Eircode and address search ("see it from the street").
 * © 2026 Elaine Walsh, Autism & Me. All rights reserved.
 *
 * What it does
 *   1. Adds "Search by Eircode or street address" to the Find a venue page.
 *   2. Opens a window on the page with a map and a view of the front of the building.
 *   3. Where the place has a published ISEE guide, "Open the door" hands over to ISEE.
 *      Where it has none, it says so. ISEE never guesses what is inside a building.
 *
 * Privacy
 *   Nothing is loaded from Google, and nothing is sent to Google, until the visitor
 *   presses "Show the map and front view". ISEE does not store what is typed.
 *   The made-up sample venues never use Google at all.
 *
 * Settings live in street-config.js.
 */
(function () {
  'use strict';

  var CFG = window.ISEE_STREET || {};
  var KEY = typeof CFG.googleMapsKey === 'string' ? CFG.googleMapsKey.trim() : '';
  var VENUES = Array.isArray(CFG.venues) ? CFG.venues : [];
  var SAMPLES = Array.isArray(CFG.samples) ? CFG.samples : [];
  var RADIUS = Number(CFG.matchRadiusMetres) > 0 ? Number(CFG.matchRadiusMetres) : 60;
  var REGION = typeof CFG.region === 'string' && CFG.region ? CFG.region : 'IE';

  var lastQuery = '';
  var googleReady = null;   // Promise, set the first time Google is asked for
  var authFailed = false;
  var runId = 0;            // guards against an older search finishing after a newer one

  /* ---------- small helpers ---------- */

  function el(tag, attrs) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === false || v === null || v === undefined) return;
        if (k === 'text') node.textContent = v;
        else if (k === 'hidden') node.hidden = !!v;
        else node.setAttribute(k, v === true ? '' : String(v));
      });
    }
    for (var i = 2; i < arguments.length; i++) {
      var child = arguments[i];
      if (child === null || child === undefined || child === false) continue;
      node.append(child);
    }
    return node;
  }

  function reducedMotion() {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function normaliseEircode(text) {
    var m = String(text || '').toUpperCase().replace(/\s+/g, '').match(/[A-Z][0-9][0-9W][0-9A-Z]{4}/);
    return m ? m[0] : '';
  }

  function metresBetween(a, b) {
    var R = 6371000, rad = Math.PI / 180;
    var dLat = (b.lat - a.lat) * rad, dLng = (b.lng - a.lng) * rad;
    var h = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
  }

  /* Compass direction, in degrees, to look from one point towards another. */
  function headingBetween(from, to) {
    var rad = Math.PI / 180;
    var y = Math.sin((to.lng - from.lng) * rad) * Math.cos(to.lat * rad);
    var x = Math.cos(from.lat * rad) * Math.sin(to.lat * rad) -
            Math.sin(from.lat * rad) * Math.cos(to.lat * rad) * Math.cos((to.lng - from.lng) * rad);
    return (Math.atan2(y, x) / rad + 360) % 360;
  }

  function googleMapsLink(query) {
    return 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(query);
  }

  /* Moves to another ISEE page. The demonstration has its own router; a hosted site uses the address bar. */
  function go(path) {
    if (window.__iseeDemo && typeof window.__iseeDemo.go === 'function') window.__iseeDemo.go(path);
    else window.location.assign(path);
  }

  /* A real venue with a published guide, matched by Eircode or by being close enough. */
  function findGuide(query, point, postcode) {
    var wanted = normaliseEircode(query) || normaliseEircode(postcode);
    for (var i = 0; i < VENUES.length; i++) {
      var v = VENUES[i];
      if (!v || !v.slug) continue;
      if (wanted && normaliseEircode(v.eircode) === wanted) return v;
      if (point && typeof v.lat === 'number' && typeof v.lng === 'number' &&
          metresBetween(point, { lat: v.lat, lng: v.lng }) <= RADIUS) return v;
    }
    return null;
  }

  /* ---------- drawings for the made-up venues (never a real place) ---------- */

  var FRONT_SVG =
    '<svg viewBox="0 0 400 300" role="img" aria-label="Drawing of the front of a building with a double door in the middle and a window on each side. It is not a real place." preserveAspectRatio="xMidYMid slice">' +
    '<rect width="400" height="300" fill="#E7EDE7"/>' +
    '<rect y="236" width="400" height="64" fill="#9CAF9C"/>' +
    '<rect x="150" y="236" width="100" height="64" fill="#F8F5EF"/>' +
    '<rect x="40" y="58" width="320" height="180" fill="#FFFFFF" stroke="#16283A" stroke-width="3"/>' +
    '<rect x="30" y="44" width="340" height="18" fill="#16283A"/>' +
    '<rect x="66" y="112" width="62" height="70" fill="#E7EDE7" stroke="#16283A" stroke-width="3"/>' +
    '<rect x="272" y="112" width="62" height="70" fill="#E7EDE7" stroke="#16283A" stroke-width="3"/>' +
    '<rect x="160" y="124" width="80" height="114" fill="#16283A"/>' +
    '<rect x="166" y="130" width="32" height="102" fill="#2B4059" stroke="#F8F5EF" stroke-width="2"/>' +
    '<rect x="202" y="130" width="32" height="102" fill="#2B4059" stroke="#F8F5EF" stroke-width="2"/>' +
    '<rect x="192" y="176" width="4" height="18" rx="2" fill="#F8F5EF"/>' +
    '<rect x="204" y="176" width="4" height="18" rx="2" fill="#F8F5EF"/>' +
    '<rect x="120" y="76" width="160" height="30" rx="4" fill="#F8F5EF" stroke="#16283A" stroke-width="2"/>' +
    '<text x="200" y="96" text-anchor="middle" font-family="Poppins, Arial, sans-serif" font-weight="700" font-size="13" fill="#16283A" data-street-sign></text>' +
    '</svg>';

  var MAP_SVG =
    '<svg viewBox="0 0 400 300" role="img" aria-label="Drawing of a simple street plan with one pin. It is not a real map." preserveAspectRatio="xMidYMid slice">' +
    '<rect width="400" height="300" fill="#E7EDE7"/>' +
    '<rect x="0" y="130" width="400" height="34" fill="#F8F5EF" stroke="#6B7C8F"/>' +
    '<rect x="120" y="0" width="30" height="300" fill="#F8F5EF" stroke="#6B7C8F"/>' +
    '<rect x="290" y="164" width="26" height="136" fill="#F8F5EF" stroke="#6B7C8F"/>' +
    '<rect x="176" y="62" width="88" height="52" fill="#FFFFFF" stroke="#16283A" stroke-width="2"/>' +
    '<path d="M220 40c-12 0-21 9-21 20 0 15 21 36 21 36s21-21 21-36c0-11-9-20-21-20z" fill="#16283A"/>' +
    '<circle cx="220" cy="60" r="7" fill="#F8F5EF"/>' +
    '</svg>';

  /* ---------- the section on the Find a venue page ---------- */

  function buildSection() {
    var input = el('input', {
      id: 'street-q', name: 'street-q', type: 'text', autocomplete: 'off', maxlength: '120',
      'aria-describedby': 'street-q-hint street-privacy', spellcheck: 'false'
    });
    input.value = lastQuery;

    var error = el('p', { class: 'street-error', id: 'street-error', role: 'alert', hidden: true });

    var form = el('form', { class: 'street-form', novalidate: true, 'aria-label': 'Search by Eircode or street address' },
      el('div', { class: 'field' },
        el('label', { for: 'street-q', text: 'Eircode or street address' }),
        el('p', { class: 'hint', id: 'street-q-hint', text: 'An Eircode looks like A65 F4E2. Or type the street and the town.' }),
        error,
        input),
      el('p', { class: 'note', id: 'street-privacy' },
        'ISEE does not keep what you type. When you press the button, what you typed is sent to Google to find the map and the street view. Google may set cookies. ',
        el('a', { href: '/privacy', text: 'Privacy' }), '.'),
      el('div', { class: 'button-row' },
        el('button', { class: 'button button-secondary', type: 'submit', text: 'Show the map and front view' })));

    var holder = el('div', { class: 'street-holder' });

    form.addEventListener('submit', function (event) {
      // Handled here only. The page's own form handler must not treat this as a venue search.
      event.preventDefault();
      event.stopPropagation();
      var query = input.value.replace(/\s+/g, ' ').trim();
      lastQuery = query;
      if (query.length < 3) {
        error.textContent = 'Type an Eircode or a street address.';
        error.hidden = false;
        input.setAttribute('aria-invalid', 'true');
        input.setAttribute('aria-describedby', 'street-error street-q-hint street-privacy');
        input.focus();
        return;
      }
      error.hidden = true;
      error.textContent = '';
      input.removeAttribute('aria-invalid');
      input.setAttribute('aria-describedby', 'street-q-hint street-privacy');
      openForAddress(holder, input, query);
    });

    var section = el('section', { class: 'card street-search', id: 'street-search', 'aria-labelledby': 'street-h' },
      el('h2', { id: 'street-h', text: 'Search by Eircode or street address' }),
      el('p', { text: 'See a place from the street before you go: a map, and a view of the front of the building. If the place has an ISEE guide, you can open the door and ISEE takes over inside.' }),
      form);

    if (SAMPLES.length) {
      var list = el('ul');
      SAMPLES.forEach(function (sample) {
        var button = el('button', { class: 'button button-secondary', type: 'button', text: sample.name });
        button.addEventListener('click', function () { openForSample(holder, button, sample); });
        list.append(el('li', null, button));
      });
      section.append(el('div', { class: 'street-samples' },
        el('h3', { text: 'Try it with a made-up venue' }),
        el('p', { class: 'note', text: 'These venues do not exist, so you see a drawing instead of a real street. Nothing is sent to Google.' }),
        list));
    }

    section.append(holder);
    return section;
  }

  /* ---------- the window ---------- */

  function buildWindow(holder, returnFocusTo, titleText) {
    runId += 1;
    var title = el('h3', { id: 'street-win-h', tabindex: '-1', text: titleText });
    var close = el('button', { class: 'button button-secondary', type: 'button', text: 'Close' });
    var status = el('p', { class: 'street-status', role: 'status', 'aria-live': 'polite' });
    var mapView = el('div', { class: 'street-view street-map' });
    var frontView = el('div', { class: 'street-view street-front' });
    var mapCaption = el('p', { class: 'street-caption' });
    var frontCaption = el('p', { class: 'street-caption' });
    var door = el('div', { class: 'street-door' });
    var links = el('p', { class: 'street-links', hidden: true });
    var panes = el('div', { class: 'street-panes' },
      el('div', { class: 'street-pane' }, el('h4', { text: 'Map' }), mapView, mapCaption),
      el('div', { class: 'street-pane' }, el('h4', { text: 'Front view' }), frontView, frontCaption));

    var win = el('div', { class: 'street-window', id: 'street-window', role: 'region', 'aria-labelledby': 'street-win-h' },
      el('div', { class: 'street-bar' }, title, close),
      el('div', { class: 'street-body' },
        status,
        panes,
        links,
        door));

    close.addEventListener('click', function () {
      runId += 1;
      holder.replaceChildren();
      if (returnFocusTo && document.contains(returnFocusTo)) returnFocusTo.focus();
    });

    holder.replaceChildren(win);
    title.focus({ preventScroll: true });
    if (win.scrollIntoView) win.scrollIntoView({ block: 'nearest' });

    return {
      id: runId, title: title, status: status, mapView: mapView, frontView: frontView,
      mapCaption: mapCaption, frontCaption: frontCaption, door: door, panes: panes, links: links
    };
  }

  function message(view, text) {
    view.replaceChildren(el('p', { class: 'street-view-message', text: text }));
  }

  function showNoGuide(ui) {
    ui.door.replaceChildren(
      el('p', null, el('span', { class: 'status status-unknown' }, el('span', { text: 'No ISEE guide for this place yet' }))),
      el('p', { text: 'ISEE can take you inside only where a venue has published a guide. It does not guess what is inside a building.' }),
      el('div', { class: 'button-row' },
        el('a', { class: 'button button-secondary', href: '/help', text: 'Ask about a guide for this place' })));
  }

  function showGuide(ui, venue, isSample) {
    var open = el('button', { class: 'button', type: 'button', text: 'Open the door' });
    var doorPath = venue.door || ('/venues/' + venue.slug);
    open.addEventListener('click', function () {
      open.disabled = true;
      openTheDoor(ui, doorPath);
    });
    ui.door.replaceChildren(
      el('p', null, el('span', { class: 'status ' + (isSample ? 'status-unknown' : 'status-confirmed') },
        el('span', { text: isSample ? 'Made-up venue with a sample ISEE guide' : 'This place has an ISEE guide' }))),
      el('p', { text: 'When you are ready, open the door. ISEE then shows you the way inside, one step at a time' +
        (venue.doorLabel ? ', starting at: ' + venue.doorLabel + '.' : '.') }),
      el('div', { class: 'button-row' },
        open,
        el('a', { href: '/venues/' + venue.slug, text: 'Read the whole guide first' })));
  }

  /* The door opens once, then ISEE takes over. With reduced motion there is no movement at all. */
  function openTheDoor(ui, path) {
    ui.status.textContent = 'The door is open. ISEE is taking over.';
    if (reducedMotion()) { go(path); return; }
    var doorway = el('div', { class: 'street-doorway', 'aria-hidden': 'true' },
      el('p', { class: 'street-doorway-name', text: 'ISEE' }),
      el('p', { class: 'street-doorway-line', text: 'Preview before you visit' }),
      el('div', { class: 'street-leaf street-leaf-left' }),
      el('div', { class: 'street-leaf street-leaf-right' }));
    ui.frontView.append(doorway);
    void doorway.offsetWidth; // let the closed door paint before it opens
    doorway.classList.add('is-open');
    window.setTimeout(function () { go(path); }, 900);
  }

  /* ---------- made-up venues: drawings only ---------- */

  function openForSample(holder, button, sample) {
    var ui = buildWindow(holder, button, sample.name);
    ui.mapView.innerHTML = MAP_SVG;       // fixed drawing written above, never visitor text
    ui.frontView.innerHTML = FRONT_SVG;   // fixed drawing written above, never visitor text
    var sign = ui.frontView.querySelector('[data-street-sign]');
    if (sign) sign.textContent = sample.name.replace(/\s*\(fictional\)\s*$/i, '');
    ui.mapCaption.textContent = 'Drawing, not a real map. This venue has a fictional address.';
    ui.frontCaption.textContent = 'Drawing, not a photo. This venue does not exist, so there is no street view.';
    ui.status.textContent = 'Showing a made-up venue.';
    showGuide(ui, sample, true);
  }

  /* ---------- real addresses: Google, only after the button is pressed ---------- */

  function loadGoogle() {
    if (googleReady) return googleReady;
    googleReady = new Promise(function (resolve, reject) {
      var callbackName = '__iseeStreetGoogleReady';
      var done = false;
      var timer = window.setTimeout(function () { if (!done) { done = true; reject(new Error('timeout')); } }, 15000);
      window.gm_authFailure = function () { authFailed = true; document.dispatchEvent(new Event('isee-street-auth-failed')); };
      window[callbackName] = function () {
        if (done) return;
        done = true;
        window.clearTimeout(timer);
        var maps = window.google && window.google.maps;
        if (!maps) { reject(new Error('missing')); return; }
        var wanted = ['maps', 'geocoding', 'streetView', 'marker'];
        var loading = typeof maps.importLibrary === 'function'
          ? Promise.all(wanted.map(function (name) { return maps.importLibrary(name).catch(function () { return null; }); }))
          : Promise.resolve([null, null, null, null]);
        loading.then(function (libs) {
          function pick(lib, name) { return (lib && lib[name]) || maps[name]; }
          resolve({
            Map: pick(libs[0], 'Map'),
            Geocoder: pick(libs[1], 'Geocoder'),
            StreetViewService: pick(libs[2], 'StreetViewService'),
            StreetViewPanorama: pick(libs[2], 'StreetViewPanorama'),
            StreetViewSource: pick(libs[2], 'StreetViewSource'),
            StreetViewPreference: pick(libs[2], 'StreetViewPreference'),
            Marker: pick(libs[3], 'Marker')
          });
        }, reject);
      };
      var script = document.createElement('script');
      script.async = true;
      script.src = 'https://maps.googleapis.com/maps/api/js?key=' + encodeURIComponent(KEY) +
        '&v=weekly&loading=async&language=en&region=' + encodeURIComponent(REGION) + '&callback=' + callbackName;
      script.onerror = function () { if (!done) { done = true; window.clearTimeout(timer); reject(new Error('network')); } };
      document.head.append(script);
    });
    googleReady.catch(function () { googleReady = null; }); // allow another try later
    return googleReady;
  }

  function plain(latLng) {
    return { lat: typeof latLng.lat === 'function' ? latLng.lat() : latLng.lat,
             lng: typeof latLng.lng === 'function' ? latLng.lng() : latLng.lng };
  }

  function postcodeOf(result) {
    var parts = (result && result.address_components) || [];
    for (var i = 0; i < parts.length; i++) {
      if ((parts[i].types || []).indexOf('postal_code') !== -1) return parts[i].long_name || '';
    }
    return '';
  }

  function findPanorama(g, point) {
    var service = new g.StreetViewService();
    var base = { location: point, radius: 60 };
    if (g.StreetViewPreference) base.preference = g.StreetViewPreference.NEAREST;
    var outdoor = g.StreetViewSource && g.StreetViewSource.OUTDOOR;
    if (!outdoor) return service.getPanorama(base);
    var withSources = Object.assign({ sources: [outdoor] }, base);
    return service.getPanorama(withSources).catch(function (err) {
      if (err && err.code === 'ZERO_RESULTS') throw err;
      return service.getPanorama(base); // an older Google version that does not know "sources"
    });
  }

  function linkOut(query, text) {
    return el('a', { href: googleMapsLink(query), target: '_blank', rel: 'noopener noreferrer', text: text });
  }

  function openForAddress(holder, input, query) {
    var ui = buildWindow(holder, input, query);
    var mine = ui.id;
    function stale() { return mine !== runId || !document.contains(ui.title); }

    // A venue can be matched by its Eircode even before Google answers.
    var early = findGuide(query, null, '');

    if (!KEY) {
      // No key yet: no empty map boxes, just a plain message and a way to see the place.
      ui.status.textContent = 'The map and street view are not switched on inside ISEE yet. You can open this address in Google Maps instead.';
      ui.panes.hidden = true;
      ui.links.hidden = false;
      ui.links.replaceChildren(linkOut(query, 'Open this address in Google Maps (opens in a new tab)'));
      if (early) showGuide(ui, early, false); else showNoGuide(ui);
      return;
    }

    ui.status.textContent = 'Finding the place.';
    message(ui.mapView, 'Loading the map.');
    message(ui.frontView, 'Loading the front view.');

    function fail(text) {
      if (stale()) return;
      ui.status.textContent = text;
      message(ui.mapView, 'No map to show.');
      message(ui.frontView, 'No front view to show.');
      ui.mapCaption.replaceChildren(linkOut(query, 'Open this address in Google Maps (opens in a new tab)'));
      ui.frontCaption.textContent = '';
      if (early) showGuide(ui, early, false); else showNoGuide(ui);
    }

    function onAuthFailed() { fail('Google did not accept the map key for this website. The map and street view cannot be shown here.'); }
    document.addEventListener('isee-street-auth-failed', onAuthFailed, { once: true });

    loadGoogle().then(function (g) {
      if (stale()) return null;
      if (authFailed) { onAuthFailed(); return null; }
      return new g.Geocoder().geocode({ address: query, region: REGION.toLowerCase() }).then(function (response) {
        if (stale()) return;
        var result = response && response.results && response.results[0];
        var types = (result && result.types) || [];
        if (!result || !result.geometry || types.indexOf('country') !== -1) {
          fail('No place was found for that Eircode or address. Check it and try again.');
          return;
        }
        var point = plain(result.geometry.location);
        var address = result.formatted_address || query;
        ui.title.textContent = address;

        var map = new g.Map(ui.mapView, {
          center: point, zoom: 17, mapTypeControl: false, streetViewControl: false,
          fullscreenControl: false, gestureHandling: 'cooperative'
        });
        if (g.Marker) new g.Marker({ map: map, position: point, title: address });
        ui.mapView.setAttribute('aria-label', 'Map of ' + address);
        ui.mapCaption.replaceChildren(linkOut(address, 'Open in Google Maps (opens in a new tab)'));

        var venue = findGuide(query, point, postcodeOf(result));
        if (venue) showGuide(ui, venue, false); else showNoGuide(ui);

        return findPanorama(g, point).then(function (found) {
          if (stale()) return;
          var data = found && found.data;
          if (!data || !data.location || !data.location.pano) throw { code: 'ZERO_RESULTS' };
          var from = data.location.latLng ? plain(data.location.latLng) : point;
          new g.StreetViewPanorama(ui.frontView, {
            pano: data.location.pano,
            pov: { heading: headingBetween(from, point), pitch: 0 },
            zoom: 0,
            addressControl: false, fullscreenControl: false, enableCloseButton: false,
            motionTracking: false, motionTrackingControl: false
          });
          ui.frontView.setAttribute('aria-label', 'Street view facing ' + address);
          ui.frontCaption.textContent = 'Google Street View, facing the address. The picture may be some years old, and the pin may not be exactly at the door.';
          ui.status.textContent = 'Showing the map and the front view.';
        }).catch(function (err) {
          if (stale()) return;
          message(ui.frontView, err && err.code === 'ZERO_RESULTS'
            ? 'Google has no street view at this spot.'
            : 'The front view could not be loaded.');
          ui.frontCaption.textContent = '';
          ui.status.textContent = 'Showing the map. There is no front view for this place.';
        });
      }, function (err) {
        fail(err && err.code === 'ZERO_RESULTS'
          ? 'No place was found for that Eircode or address. Check it and try again.'
          : 'The place could not be looked up just now. Try again in a moment.');
      });
    }, function () {
      fail('Google Maps could not be loaded. Check your connection and try again.');
    }).then(function () {
      document.removeEventListener('isee-street-auth-failed', onAuthFailed);
    }, function () {
      document.removeEventListener('isee-street-auth-failed', onAuthFailed);
      fail('The map could not be shown just now. Try again in a moment.');
    });
  }

  /* ---------- keep the privacy page true ---------- */

  function patchPrivacy(app) {
    var heading = app.querySelector('main h1');
    if (!heading || heading.textContent.trim() !== 'Privacy') return;
    if (app.querySelector('[data-street-privacy]')) return;
    var items = app.querySelectorAll('main li');
    for (var i = 0; i < items.length; i++) {
      if (items[i].textContent.indexOf('No requests to other websites') === 0) {
        items[i].append(el('span', { 'data-street-privacy': true,
          text: ' There is one exception. If you use the Eircode and address search and press “Show the map and front view”, what you typed is sent to Google, and the map and street view load from Google. Google may set cookies. ISEE does not keep what you typed.' }));
        return;
      }
    }
  }

  /* ---------- put the section on the page whenever Find a venue is shown ---------- */

  function enhance() {
    var app = document.getElementById('demo-app') || document.body;
    patchPrivacy(app);
    var search = app.querySelector('form.search-form[action="/venues"]');
    if (!search || app.querySelector('#street-search')) return;
    search.insertAdjacentElement('afterend', buildSection());
  }

  // The demonstration swaps the children of #demo-app on every page change. Watching only that
  // (not everything inside it) keeps this quiet while a map is being moved around.
  var appRoot = document.getElementById('demo-app');
  var queued = false;
  new MutationObserver(function () {
    if (queued) return;
    queued = true;
    window.requestAnimationFrame(function () { queued = false; enhance(); });
  }).observe(appRoot || document.getElementById('demo-root') || document.body,
    appRoot ? { childList: true } : { childList: true, subtree: true });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', enhance);
  else enhance();
})();
