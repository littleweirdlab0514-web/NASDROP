globalThis.NASDropPolling = {
  active: new Set(['inspecting','queued','ready','downloading','waiting_processing','verifying','extracting','publishing','stopping']),
  create({load, onData, onError, visible = () => true, schedule = setTimeout, cancel = clearTimeout}) {
    let enabled = false, timer = null, flight = null, generation = 0, failures = 0;
    function clear() { if (timer !== null) cancel(timer); timer = null; }
    function later(delay) { clear(); if (enabled && visible()) timer = schedule(refresh, delay); }
    function stop() { enabled = false; generation++; clear(); }
    function refresh() {
      if (flight) return flight;
      if (!enabled || !visible()) return Promise.resolve();
      clear();
      const epoch = generation;
      flight = (async () => {
        let delay = 15000;
        try {
          const data = await load();
          if (!enabled || generation !== epoch) return;
          failures = 0;
          onData(data);
          delay = data.jobs.some(job => globalThis.NASDropPolling.active.has(job.status)) ? 5000 : 15000;
        } catch (error) {
          if (!enabled || generation !== epoch) return;
          failures++;
          delay = Math.min(60000, 5000 * 2 ** failures);
          onError(error);
          if (error.status === 401) stop();
        } finally {
          flight = null;
          if (enabled) later(generation === epoch ? delay : 0);
        }
      })();
      return flight;
    }
    return {
      start(immediate = true) { enabled = true; clear(); if (immediate) return refresh(); later(5000); },
      refresh,
      stop,
      visibilityChanged() { clear(); if (enabled && visible()) return refresh(); },
    };
  },
};
