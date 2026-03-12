/**
 * Character body rendering — now handled by sprite-data.ts pixel maps.
 * This file is kept for module compatibility but exports are unused.
 * See sprite-data.ts for the bitmap sprite definitions.
 */

// Body rendering is now done via pixel map in sprite-data.ts
// These exports are kept as no-ops for backward compatibility
export function drawLegs() { /* no-op: rendered via sprite data */ }
export function drawBody() { /* no-op: rendered via sprite data */ }
export function drawArms() { /* no-op: rendered via sprite data */ }
