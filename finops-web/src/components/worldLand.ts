/**
 * A coarse world, as longitude and latitude. FEAT-061.
 *
 * **Why coordinates are safe here when a region coordinate table is not.** `check_hardcoded.py`
 * forbids region literals because a table naming `eu-west-1` and `eu-west-2` makes the next region
 * a provider opens invisible until somebody notices: it is a fact about somebody else's estate,
 * and it goes stale. A coastline is a fact about the world. Nothing a cloud provider does changes
 * where Africa is, so this is written down once and never maintained, which is the exact property
 * the region table lacked.
 *
 * **Deliberately coarse, and that is the honesty.** These outlines are hand authored at roughly
 * thirty points a continent. They are recognisable and they are obviously not cartography, which
 * is what a reader should conclude: the drawing places a marker on a continent, and the caption
 * says a marker is a continent and not a datacentre. A precise coastline would invite the reading
 * that the dot is where the datacentre is, and it would also be a dataset, a dependency and a
 * projection library for what is ultimately a backdrop.
 *
 * Longitude first, then latitude, which is the order every geographic format uses and the reverse
 * of the order people say them in. Written that way rather than converted, because a list of pairs
 * that is subtly transposed draws a world nobody recognises and is very hard to read back.
 */

export type Ring = readonly (readonly [number, number])[];

//: North America, Alaska round to Panama and back up the Pacific coast.
const NORTH_AMERICA: Ring = [
  [-168, 66],
  [-160, 71],
  [-130, 70],
  [-110, 68],
  [-95, 72],
  [-80, 73],
  [-65, 66],
  [-57, 54],
  [-53, 47],
  [-66, 45],
  [-70, 41],
  [-75, 36],
  [-81, 31],
  [-80, 25],
  [-85, 30],
  [-89, 29],
  [-94, 29],
  [-97, 26],
  [-92, 19],
  [-88, 16],
  [-84, 10],
  [-78, 8],
  [-86, 13],
  [-95, 16],
  [-105, 20],
  [-110, 24],
  [-114, 29],
  [-117, 33],
  [-122, 38],
  [-124, 46],
  [-131, 54],
  [-140, 59],
  [-150, 59],
  [-160, 56],
  [-165, 60],
];

const GREENLAND: Ring = [
  [-45, 60],
  [-52, 66],
  [-57, 71],
  [-60, 76],
  [-50, 82],
  [-30, 83],
  [-20, 80],
  [-22, 72],
  [-32, 67],
  [-38, 63],
];

const SOUTH_AMERICA: Ring = [
  [-77, 8],
  [-72, 11],
  [-64, 10],
  [-60, 8],
  [-51, 0],
  [-44, -3],
  [-38, -5],
  [-35, -8],
  [-39, -14],
  [-41, -22],
  [-48, -25],
  [-54, -34],
  [-58, -38],
  [-62, -40],
  [-65, -45],
  [-68, -52],
  [-70, -55],
  [-75, -50],
  [-74, -44],
  [-73, -37],
  [-71, -30],
  [-70, -23],
  [-71, -18],
  [-77, -12],
  [-81, -5],
  [-80, 0],
  [-78, 5],
];

const AFRICA: Ring = [
  [-17, 21],
  [-16, 14],
  [-13, 9],
  [-8, 5],
  [0, 5],
  [6, 4],
  [9, 4],
  [9, 0],
  [12, -5],
  [12, -12],
  [14, -17],
  [17, -23],
  [18, -29],
  [20, -35],
  [26, -34],
  [32, -29],
  [35, -24],
  [40, -16],
  [41, -10],
  [43, -2],
  [51, 11],
  [44, 11],
  [39, 15],
  [37, 22],
  [34, 28],
  [32, 31],
  [25, 32],
  [18, 31],
  [11, 33],
  [3, 36],
  [-2, 35],
  [-6, 36],
  [-10, 30],
  [-13, 27],
];

const MADAGASCAR: Ring = [
  [43, -12],
  [50, -15],
  [50, -25],
  [46, -25],
  [44, -19],
];

//: Eurasia as one ring. Europe and Asia share a coastline and no border between them is drawn on
//: any coast, so splitting them would mean inventing a line down the Urals that nothing here uses.
const EURASIA: Ring = [
  [-9, 39],
  [-9, 43],
  [-2, 43],
  [0, 47],
  [-4, 48],
  [2, 51],
  [8, 54],
  [10, 57],
  [5, 60],
  [12, 65],
  [18, 69],
  [28, 70],
  [40, 68],
  [60, 70],
  [75, 73],
  [100, 76],
  [110, 74],
  [130, 71],
  [145, 70],
  [160, 69],
  [170, 66],
  [178, 65],
  [170, 60],
  [162, 60],
  [155, 55],
  [143, 53],
  [140, 45],
  [130, 43],
  [126, 38],
  [122, 31],
  [118, 24],
  [110, 20],
  [105, 10],
  [100, 6],
  [98, 14],
  [94, 18],
  [88, 21],
  [80, 15],
  [77, 8],
  [72, 20],
  [68, 24],
  [60, 25],
  [57, 26],
  [52, 28],
  [48, 30],
  [43, 30],
  [35, 30],
  [35, 36],
  [30, 40],
  [26, 40],
  [23, 38],
  [20, 40],
  [16, 41],
  [12, 38],
  [14, 42],
  [10, 44],
  [4, 43],
  [0, 39],
  [-6, 37],
];

const BRITAIN: Ring = [
  [-5, 50],
  [-2, 51],
  [0, 53],
  [-1, 55],
  [-3, 58],
  [-6, 58],
  [-5, 54],
];

const JAPAN: Ring = [
  [130, 33],
  [136, 35],
  [140, 36],
  [142, 41],
  [145, 44],
  [141, 45],
  [138, 37],
  [133, 34],
];

const AUSTRALIA: Ring = [
  [114, -22],
  [114, -26],
  [116, -35],
  [120, -34],
  [129, -32],
  [135, -35],
  [138, -35],
  [141, -38],
  [146, -39],
  [150, -37],
  [153, -28],
  [153, -25],
  [146, -19],
  [142, -11],
  [136, -12],
  [132, -11],
  [130, -13],
  [125, -14],
  [121, -20],
];

const NEW_ZEALAND: Ring = [
  [173, -35],
  [178, -38],
  [177, -40],
  [172, -41],
  [170, -44],
  [167, -46],
  [170, -45],
  [172, -40],
];

export const LAND: readonly Ring[] = [
  NORTH_AMERICA,
  GREENLAND,
  SOUTH_AMERICA,
  AFRICA,
  MADAGASCAR,
  EURASIA,
  BRITAIN,
  JAPAN,
  AUSTRALIA,
  NEW_ZEALAND,
];

/**
 * Where each geography's marker sits.
 *
 * A point on a continent, never on a city, which is the same claim the caption makes. Written in
 * the same longitude and latitude as the land so a marker and the coast under it cannot drift
 * apart: a marker in fractions of the drawing and a coast in degrees would need two changes every
 * time the projection moved, and one of them would eventually be forgotten.
 */
export const ANCHORS: Readonly<Record<string, readonly [number, number]>> = {
  us: [-98, 39],
  ca: [-106, 58],
  sa: [-58, -12],
  eu: [10, 50],
  af: [20, 2],
  il: [35, 31],
  me: [50, 25],
  cn: [105, 36],
  ap: [112, -6],
};
