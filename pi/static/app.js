const voltageEl = document.getElementById('voltage');
const currentEl = document.getElementById('current');
const powerEl = document.getElementById('power');
const tempFrontEl = document.getElementById('tempFront');
const tempBackEl = document.getElementById('tempBack');
const energyEl = document.getElementById('energy');
const statusEl = document.getElementById('status');

function makeChart(ctx, label, color) {
  return new Chart(ctx, {
    type: 'line',
    data: { labels: [], datasets: [{ label, data: [], borderColor: color, tension: 0.15 }] },
    options: {
      animation: false,
      responsive: true,
      scales: { x: { ticks: { maxTicksLimit: 8 } } }
    }
  });
}

const powerChart = makeChart(document.getElementById('powerChart'), 'Power (W)', '#22d3ee');
const voltageChart = makeChart(document.getElementById('voltageChart'), 'Voltage (V)', '#f59e0b');

function updateDom(latest) {
  voltageEl.textContent = latest.voltage_v.toFixed(2);
  currentEl.textContent = latest.current_a.toFixed(2);
  powerEl.textContent = latest.power_w.toFixed(1);
  tempFrontEl.textContent = latest.temp_front_c.toFixed(1);
  tempBackEl.textContent = latest.temp_back_c.toFixed(1);
  energyEl.textContent = latest.energy_wh_day.toFixed(2);
}

function updateCharts(history) {
  const labels = history.map(x => x.timestamp.slice(11));
  powerChart.data.labels = labels;
  voltageChart.data.labels = labels;

  powerChart.data.datasets[0].data = history.map(x => x.power_w);
  voltageChart.data.datasets[0].data = history.map(x => x.voltage_v);

  powerChart.update('none');
  voltageChart.update('none');
}

async function poll() {
  try {
    const res = await fetch('/api/latest');
    const data = await res.json();

    if (!data.latest) {
      statusEl.textContent = 'Waiting for incoming samples...';
      return;
    }

    updateDom(data.latest);
    updateCharts(data.history);

    if (data.status.stale) {
      statusEl.textContent = 'No fresh data (check serial link).';
    } else {
      statusEl.textContent = data.status.last_error ? `Warning: ${data.status.last_error}` : 'Live';
    }
  } catch (err) {
    statusEl.textContent = `API error: ${err.message}`;
  }
}

poll();
setInterval(poll, 1000);
