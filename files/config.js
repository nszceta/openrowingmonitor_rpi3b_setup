'use strict'
/*
  Open Rowing Monitor configuration for a Concept2 RowErg (Model D/E/RowErg).
  See https://github.com/JaapvanEkris/openrowingmonitor/blob/main/docs/hardware_setup_Concept2_RowErg.md
*/
import rowerProfiles from './rowerProfiles.js'

export default {
  loglevel: {
    default: 'info'
  },

  // Official Concept2 RowErg profile (flywheel sensor via optocoupler on GPIO 17)
  rowerSettings: {
    ...rowerProfiles.Concept2_RowErg,
    // Allow weaker pulls to pass the startup flywheel-speed gate.
    maximumTimeBetweenImpulses: 0.018
  },

  // Armbian kernel is PREEMPT (6.18.35-current-bcm2711) — official perf doc allows up to -7/-5.
  // Root runs the service, so os.setPriority() works.
  gpioPriority: -5,
  appPriority: -2,

  // BLE profile broadcast to rowing apps (EXR, ErgZone, Kinomap). 'PM5' emulation is
  // available but not functionally complete; FTMS is the tested default.
  bluetoothMode: 'FTMS'
}
