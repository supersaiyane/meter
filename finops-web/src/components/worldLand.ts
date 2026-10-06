/**
 * Where each geography's marker sits on the map. FEAT-061.
 *
 * A point on a continent, never on a city, which is the same claim the caption makes: the region
 * name prefix says Europe and cannot say Dublin.
 *
 * Longitude first, then latitude, which is the order every geographic format uses and the reverse
 * of the order people say them in. The same order `worldDots.ts` was generated from, so a bubble
 * and the land under it cannot drift apart.
 *
 * A place with no anchor here is not dropped: `WorldMap` leaves it off the drawing, keeps it in
 * the legend and counts it in a sentence. So adding a geography to the domain without adding an
 * anchor degrades honestly rather than losing an estate's worth of resources.
 *
 * This file used to hold hand written coastlines too. They were written out from memory and drew
 * shapes nobody recognised, so the outlines are generated from Natural Earth now and only the
 * anchors are a judgement.
 */

export const ANCHORS: Readonly<Record<string, readonly [number, number]>> = {
  us: [-98, 39],
  ca: [-106, 58],
  mx: [-102, 23],
  sa: [-58, -12],
  eu: [10, 50],
  af: [20, 2],
  il: [35, 31],
  me: [50, 25],
  cn: [105, 36],
  ap: [112, -6],
};
