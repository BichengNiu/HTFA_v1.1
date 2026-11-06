"""Browser controls for the embedded Leaflet map (no server credentials)."""

SCREENSHOT_SCRIPT = r"""
function loadHtml2Canvas() {
  if (typeof window.html2canvas === 'function') return Promise.resolve();
  if (!window.html2canvasPromise) {
    window.html2canvasPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://unpkg.com/html2canvas@1.4.1/dist/html2canvas.min.js';
      script.onload = resolve;
      script.onerror = () => {
        window.html2canvasPromise = null;
        reject(new Error('截图组件加载失败'));
      };
      document.head.appendChild(script);
    });
  }
  return window.html2canvasPromise;
}
window.saveMapPng = async () => {
  let status = document.getElementById('save-status');
  if (!status) {
    const screenshotControl = L.control({position: 'topright'});
    screenshotControl.onAdd = () => {
      const el = L.DomUtil.create('div', 'map-tools');
      el.setAttribute('data-html2canvas-ignore', 'true');
      el.innerHTML = '<span id="save-status" role="status" aria-live="polite"></span>';
      return el;
    };
    screenshotControl.addTo(map);
    status = document.getElementById('save-status');
  }
  status.textContent = '正在生成…';
  try {
    await loadHtml2Canvas();
    await document.fonts.ready;
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const tileImages = [...document.querySelectorAll('#map .leaflet-tile')];
    await Promise.race([
      Promise.all(tileImages.map(img => img.decode())),
      new Promise((resolve, reject) => setTimeout(() => reject(new Error('底图加载超时')), 15000))
    ]);
    if (!tileImages.length || tileImages.some(img => !img.naturalWidth)) {
      throw new Error('底图未加载完成，请等待后重试');
    }
    const canvas = await window.html2canvas(document.getElementById('map'), {
      useCORS: true, allowTaint: false, backgroundColor: '#e8eef4',
      scale: Math.min(window.devicePixelRatio || 1, 2), logging: false,
      imageTimeout: 15000
    });
    const blob = await new Promise((resolve, reject) => canvas.toBlob(
      value => value ? resolve(value) : reject(new Error('图片编码失败')), 'image/png'));
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `energy-map_${screenshotDate}_${new Date().toISOString().replace(/[:.]/g, '-')}.png`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    status.textContent = 'PNG 已生成';
  } catch (error) {
    status.textContent = `保存失败：${error.message || error}。可使用浏览器截图。`;
  }
};
"""
