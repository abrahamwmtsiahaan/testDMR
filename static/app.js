"use strict";

/* ===================== UTILITAS ===================== */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

function toast(pesan, err = false) {
  const t = $("#toast");
  t.textContent = pesan;
  t.className = "tampil" + (err ? " err" : "");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.className = ""), 3500);
}

function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      })[c],
  );
}

/* ===================== MODAL DIALOG ===================== */
function tampilModal({
  judul = "Konfirmasi",
  pesan = "",
  tipe = "warning", // 'warning', 'danger', 'info', 'sukses'
  tombolKonfirmasi = "Lanjutkan",
  tombolBatal = "Batal",
  tombolSekunder = null,
  warnaKonfirmasi = "utama", // 'utama' | 'danger'
}) {
  return new Promise((resolve) => {
    const backdrop = $("#modal-dialog");
    const ikonEl = $("#modal-ikon");
    const judulEl = $("#modal-judul");
    const pesanEl = $("#modal-pesan");
    const aksiEl = $("#modal-aksi");

    judulEl.textContent = judul;
    pesanEl.innerHTML = pesan;

    ikonEl.className = "modal-ikon " + tipe;
    if (tipe === "danger") ikonEl.textContent = "✕";
    else if (tipe === "sukses") ikonEl.textContent = "✓";
    else if (tipe === "info") ikonEl.textContent = "ℹ";
    else ikonEl.textContent = "⚠️";

    aksiEl.innerHTML = "";

    if (tombolSekunder) {
      const btnSek = document.createElement("button");
      btnSek.className = "btn-sekunder";
      btnSek.type = "button";
      btnSek.textContent = tombolSekunder;
      btnSek.onclick = () => {
        tutup();
        resolve("sekunder");
      };
      aksiEl.appendChild(btnSek);
    }

    if (tombolBatal) {
      const btnBatal = document.createElement("button");
      btnBatal.className = "btn-batal";
      btnBatal.type = "button";
      btnBatal.textContent = tombolBatal;
      btnBatal.onclick = () => {
        tutup();
        resolve(false);
      };
      aksiEl.appendChild(btnBatal);
    }

    if (tombolKonfirmasi) {
      const btnKonf = document.createElement("button");
      btnKonf.className = warnaKonfirmasi === "danger" ? "btn-danger" : "utama";
      btnKonf.type = "button";
      btnKonf.textContent = tombolKonfirmasi;
      btnKonf.onclick = () => {
        tutup();
        resolve(true);
      };
      aksiEl.appendChild(btnKonf);
    }

    function tutup() {
      backdrop.hidden = true;
      document.removeEventListener("keydown", onKeyDown);
    }

    function onKeyDown(e) {
      if (e.key === "Escape") {
        tutup();
        resolve(false);
      }
    }
    document.addEventListener("keydown", onKeyDown);

    backdrop.hidden = false;
  });
}

async function api(url, opsi = {}) {
  const r = await fetch(url, opsi);
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return r;
}
const apiJson = async (url, opsi) => (await api(url, opsi)).json();
const kirimJson = (url, body) =>
  apiJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

function muatGambar(url) {
  return new Promise((res, rej) => {
    const im = new Image();
    im.onload = () => res(im);
    im.onerror = () => rej(new Error("Gambar gagal dimuat"));
    im.src = url + (url.includes("?") ? "&" : "?") + "t=" + Date.now();
  });
}

/* ===================== KANVAS ZOOM/GESER ===================== */
class KanvasGambar {
  constructor(canvas, wrap) {
    this.c = canvas;
    this.wrap = wrap;
    this.ctx = canvas.getContext("2d");
    this.img = null;
    this.skala = 1;
    this.ox = 0;
    this.oy = 0;
    this.overlay = null; // fungsi(ctx, kanvas) menggambar di ruang gambar
    this.onKlik = null; // fungsi(xGambar, yGambar)
    this.onGerak = null; // fungsi(xGambar, yGambar) | null
    this._geser = null;
    this._spasi = false;
    this._pasang();
    new ResizeObserver(() => this.ukuran()).observe(wrap);
  }
  _pasang() {
    const c = this.c;
    c.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        const f = e.deltaY < 0 ? 1.15 : 1 / 1.15;
        this.zoomDi(e.offsetX, e.offsetY, f);
      },
      { passive: false },
    );
    c.addEventListener("contextmenu", (e) => e.preventDefault());
    c.addEventListener("mousedown", (e) => {
      if (e.button === 2 || e.button === 1 || this._spasi) {
        this._geser = { x: e.clientX, y: e.clientY, ox: this.ox, oy: this.oy };
        c.style.cursor = "grabbing";
        e.preventDefault();
      } else if (e.button === 0) {
        this._down = { x: e.clientX, y: e.clientY };
      }
    });
    window.addEventListener("mousemove", (e) => {
      if (this._geser) {
        this.ox = this._geser.ox + (e.clientX - this._geser.x);
        this.oy = this._geser.oy + (e.clientY - this._geser.y);
        this.gambar();
      }
    });
    window.addEventListener("mouseup", (e) => {
      if (this._geser) {
        this._geser = null;
        c.style.cursor = "crosshair";
        return;
      }
      if (this._down && e.button === 0) {
        const jarak = Math.hypot(
          e.clientX - this._down.x,
          e.clientY - this._down.y,
        );
        if (jarak < 5 && e.target === c) {
          const p = this.keGambar(e.offsetX, e.offsetY);
          if (this.onKlik) this.onKlik(p.x, p.y);
        }
        this._down = null;
      }
    });
    c.addEventListener("mousemove", (e) => {
      if (this.onGerak && !this._geser) {
        const p = this.keGambar(e.offsetX, e.offsetY);
        this.onGerak(p.x, p.y, e);
      }
    });
    c.addEventListener(
      "mouseleave",
      () => this.onGerak && this.onGerak(null, null),
    );
    window.addEventListener("keydown", (e) => {
      if (e.code === "Space" && this._aktif()) {
        this._spasi = true;
        this.c.style.cursor = "grab";
        e.preventDefault();
      }
    });
    window.addEventListener("keyup", (e) => {
      if (e.code === "Space") {
        this._spasi = false;
        this.c.style.cursor = "crosshair";
      }
    });
  }
  _aktif() {
    return (
      this.c.offsetParent !== null &&
      !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)
    );
  }
  ukuran() {
    const r = this.wrap.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.c.width = Math.max(1, Math.floor(r.width * dpr));
    this.c.height = Math.max(1, Math.floor(r.height * dpr));
    this.dpr = dpr;
    this.gambar();
  }
  set(img) {
    this.img = img;
    this.ukuran();
    this.pas();
  }
  pas() {
    if (!this.img) return;
    const w = this.c.width / this.dpr,
      h = this.c.height / this.dpr;
    this.skala = Math.min(w / this.img.width, h / this.img.height) * 0.98;
    this.ox = (w - this.img.width * this.skala) / 2;
    this.oy = (h - this.img.height * this.skala) / 2;
    this.gambar();
  }
  zoomDi(x, y, f) {
    const baru = Math.min(Math.max(this.skala * f, 0.03), 12);
    f = baru / this.skala;
    this.ox = x - (x - this.ox) * f;
    this.oy = y - (y - this.oy) * f;
    this.skala = baru;
    this.gambar();
  }
  zoomTengah(f) {
    this.zoomDi(this.c.width / this.dpr / 2, this.c.height / this.dpr / 2, f);
  }
  keGambar(x, y) {
    return { x: (x - this.ox) / this.skala, y: (y - this.oy) / this.skala };
  }
  keLayar(x, y) {
    return { x: x * this.skala + this.ox, y: y * this.skala + this.oy };
  }
  gambar() {
    const ctx = this.ctx;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.c.width, this.c.height);
    if (!this.img) return;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(
      this.img,
      this.ox,
      this.oy,
      this.img.width * this.skala,
      this.img.height * this.skala,
    );
    if (this.overlay) {
      ctx.save();
      ctx.translate(this.ox, this.oy);
      ctx.scale(this.skala, this.skala);
      this.overlay(ctx, this.skala);
      ctx.restore();
    }
  }
}

/* ===================== STATE ===================== */
const S = {
  status: { scanner: null },
  template: { nama: "", kriteria: [], contohUrl: null, contohImg: null },
  templateSnapshot: null,
  kalibrasi: { idx: -1, klik: [], aktif: false },
  sesi: null, // { sesi, lembar: [...] }
  templateSesi: null, // template yang dipakai sesi (untuk label & grid)
  dipilih: -1,
  lembarDipilih: new Set(),
};

/* ===================== PELACAKAN PERUBAHAN TEMPLATE ===================== */
function getTemplateSnapshot() {
  const kriteria = (S.template.kriteria || []).map((k) => ({
    nama: (k.nama || "").trim(),
    arah_baca: k.arah_baca,
    jumlah_kolom: Number(k.jumlah_kolom) || 1,
    jumlah_baris: Number(k.jumlah_baris) || 1,
    jenis_label: k.jenis_label,
    label_kustom: (k.label_kustom || "").trim(),
    label_baris: Array.isArray(k.label_baris) ? [...k.label_baris] : [],
    grid: k.grid
      ? {
          x0: Math.round((k.grid.x0 || 0) * 100) / 100,
          y0: Math.round((k.grid.y0 || 0) * 100) / 100,
          dx: Math.round((k.grid.dx || 0) * 100) / 100,
          dy: Math.round((k.grid.dy || 0) * 100) / 100,
        }
      : null,
  }));

  return JSON.stringify({
    nama: ($("#nama-template")?.value || "").trim(),
    contohUrl: S.template.contohUrl || null,
    kriteria,
  });
}

function catatSnapshotTemplate() {
  S.templateSnapshot = getTemplateSnapshot();
  perbaruiIndikatorSimpan();
}

function isTemplateDirty() {
  if (S.templateSnapshot === undefined || S.templateSnapshot === null) return false;
  return S.templateSnapshot !== getTemplateSnapshot();
}

function perbaruiIndikatorSimpan() {
  const el = $("#info-template");
  if (!el) return;
  if (isTemplateDirty()) {
    if (!el.classList.contains("err")) {
      el.className = "info";
      el.innerHTML = `<span style="color:#d97706; font-weight:600;">● Perubahan belum disimpan. Klik "Simpan template".</span>`;
    }
  } else {
    if (el.innerHTML.includes("Perubahan belum disimpan")) {
      el.innerHTML = "";
    }
  }
}

/* ===================== NAVIGASI TAB ===================== */
async function bukaTab(nama, abaikanDirty = false) {
  const tabSekarang = $(".tab.aktif")?.id?.replace("tab-", "") || "template";

  if (tabSekarang === "template" && nama !== "template" && !abaikanDirty && isTemplateDirty()) {
    const namaTujuan =
      {
        scan: "Step 2 (Scan)",
        periksa: "Step 3 (Periksa)",
        simpan: "Step 4 (Simpan)",
      }[nama] || "step berikutnya";

    const aksi = await tampilModal({
      judul: "Simpan Template Terlebih Dahulu",
      pesan: `Terdapat perubahan pada template di <b>Step 1</b> (posisi bulatan, arah baca, kotak/bulatan, isi bulatan, atau bagian) yang belum disimpan.<br><br>Harap simpan perubahan pada <b>Step 1 ("Simpan template")</b> terlebih dahulu sebelum melanjutkan ke <b>${namaTujuan}</b>.
      <div class="highlight-box">
        Klik <b>"Simpan Template &amp; Lanjut"</b> untuk menyimpan perubahan secara otomatis dan melanjutkan ke ${namaTujuan}.
      </div>`,
      tipe: "warning",
      tombolKonfirmasi: "Simpan Template & Lanjut",
      tombolBatal: "Batal (Tetap di Step 1)",
      tombolSekunder: "Lanjut Tanpa Menyimpan",
    });

    if (aksi === true) {
      const sukses = await simpanTemplate();
      if (!sukses) return;
      await bukaTab(nama, true);
      return;
    } else if (aksi === "sekunder") {
      await bukaTab(nama, true);
      return;
    } else {
      const btnSimpan = $("#btn-simpan-template");
      if (btnSimpan) {
        btnSimpan.scrollIntoView({ behavior: "smooth", block: "center" });
        btnSimpan.classList.add("sorot-simpan");
        setTimeout(() => btnSimpan.classList.remove("sorot-simpan"), 2000);
      }
      return;
    }
  }

  $$("#nav button").forEach((b) =>
    b.classList.toggle("aktif", b.dataset.tab === nama),
  );
  $$(".tab").forEach((t) =>
    t.classList.toggle("aktif", t.id === "tab-" + nama),
  );
  if (nama === "simpan") {
    renderTabSimpan();
  }
  requestAnimationFrame(() => {
    kalib.ukuran();
    detail.ukuran();
  });
}
$$("#nav button").forEach((b) =>
  b.addEventListener("click", () => bukaTab(b.dataset.tab)),
);

/* ===================== STATUS SCANNER ===================== */
async function muatStatus() {
  const el = $("#status-scanner");
  try {
    S.status = await apiJson("/api/status");
    if (S.status.scanner) {
      el.textContent = "Scanner: " + S.status.scanner;
      el.className = "status ok";
    } else {
      el.textContent = "Scanner tidak terdeteksi (mode unggah)";
      el.className = "status mati";
    }
  } catch (e) {
    el.textContent = "Server tidak merespons";
    el.className = "status mati";
  }
  const ada = !!S.status.scanner;
  $("#blok-scanner").hidden = !ada;
  $("#atau").hidden = !ada;
  $("#btn-scan-contoh").hidden = !ada;
}

/* ===================== TAB 1: TEMPLATE ===================== */
const kalib = new KanvasGambar($("#kanvas-kalibrasi"), $("#wrap-kalibrasi"));
const kaca = { el: $("#kaca"), c: $("#kaca-kanvas") };

$("#zoom-in").onclick = () => kalib.zoomTengah(1.3);
$("#zoom-out").onclick = () => kalib.zoomTengah(1 / 1.3);
$("#zoom-pas").onclick = () => kalib.pas();

const LABEL_JENIS = {
  huruf: "Huruf A, B, C…",
  angka0: "Angka 0, 1, 2…",
  angka1: "Angka 1, 2, 3…",
  kustom: "Ketik sendiri",
};

function buatLabel(jenis, n, kustom) {
  if (jenis === "huruf")
    return Array.from({ length: n }, (_, i) => String.fromCharCode(65 + i));
  if (jenis === "angka0") return Array.from({ length: n }, (_, i) => String(i));
  if (jenis === "angka1")
    return Array.from({ length: n }, (_, i) => String(i + 1));
  return (kustom || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function tambahBagian(data) {
  const arah = data?.arah_baca || "vertikal";
  const kol = data?.jumlah_kolom || 10;
  const bar = data?.jumlah_baris || 10;
  const jenis = data?.jenis_label || "angka0";
  const butuh = arah === "horizontal" ? kol : bar;
  const kustom = data?.label_kustom || "";
  S.template.kriteria.push(
    Object.assign(
      {
        nama: "bagian_" + (S.template.kriteria.length + 1),
        arah_baca: arah,
        jumlah_kolom: kol,
        jumlah_baris: bar,
        jenis_label: jenis,
        label_kustom: kustom,
        label_baris: data?.label_baris || buatLabel(jenis, butuh, kustom),
        grid: null,
      },
      data || {},
    ),
  );
  renderBagian();
}

function renderBagian() {
  const w = $("#daftar-bagian");
  w.innerHTML = "";
  S.template.kriteria.forEach((k, i) => {
    const d = document.createElement("div");
    d.className = "bagian" + (i === S.kalibrasi.idx ? " terpilih" : "");
    d.innerHTML = `
      <div class="bagian-atas">
        <input type="text" value="${k.nama}" data-f="nama" placeholder="Nama bagian">
        <button class="hapus" title="Hapus" data-hapus>✕</button>
      </div>
      <div class="dua" style="margin-bottom:6px">
        <div><label>Arah baca</label>
          <select data-f="arah_baca">
            <option value="vertikal" ${k.arah_baca !== "horizontal" ? "selected" : ""}>↓ Ke bawah (Vertikal)</option>
            <option value="horizontal" ${k.arah_baca === "horizontal" ? "selected" : ""}>→ Ke samping (Horizontal)</option>
          </select>
        </div>
      </div>
      <div class="dua">
        <div><label>Kotak ke samping</label><input type="number" min="1" value="${k.jumlah_kolom}" data-f="jumlah_kolom"></div>
        <div><label>Bulatan ke bawah</label><input type="number" min="1" value="${k.jumlah_baris}" data-f="jumlah_baris"></div>
      </div>
      <div class="lbl-kustom">
        <label>Isi bulatan pilihan</label>
        <select data-f="jenis_label">
          ${Object.entries(LABEL_JENIS)
            .map(
              ([v, t]) =>
                `<option value="${v}" ${k.jenis_label === v ? "selected" : ""}>${t}</option>`,
            )
            .join("")}
        </select>
        <input type="text" data-f="label_kustom" placeholder="mis. A,B,C,D,E" value="${k.label_kustom || ""}" style="margin-top:6px" ${k.jenis_label === "kustom" ? "" : "hidden"}>
      </div>
      <div class="aksi">
        <button class="kecil utama" data-tandai>Tandai posisi</button>
        <span class="tag ${k.grid ? "ok" : "belum"}">${k.grid ? "Sudah ditandai" : "Belum ditandai"}</span>
      </div>`;
    const tanganiInput = async (e) => {
      const f = e.target.dataset.f;
      if (!f) return;
      let v = e.target.value;
      if (f === "jumlah_kolom" || f === "jumlah_baris") {
        if (e.type === "input") return;
        v = Math.max(1, parseInt(v) || 1);
      }
      if (f === "nama") v = v.trim().toLowerCase().replace(/\s+/g, "_");

      if (["arah_baca", "jenis_label"].includes(f) && e.type === "input") return;

      if (k[f] === v) return;

      if (
        k.grid &&
        ["arah_baca", "jumlah_kolom", "jumlah_baris", "jenis_label"].includes(f)
      ) {
        const labelField =
          {
            arah_baca: "arah baca",
            jumlah_kolom: "kotak ke samping",
            jumlah_baris: "bulatan ke bawah",
            jenis_label: "isi bulatan pilihan",
          }[f] || f;

        const yakin = await tampilModal({
          judul: `Ubah ${labelField.charAt(0).toUpperCase() + labelField.slice(1)}?`,
          pesan: `Bagian <b>"${escapeHtml(k.nama)}"</b> sudah ditandai posisinya. Mengubah <b>${labelField}</b> akan mereset posisi yang telah ditandai.<br><br>Apakah Anda yakin ingin mengubah bagian ini?`,
          tipe: "warning",
          tombolKonfirmasi: "Ya, Ubah",
          tombolBatal: "Batal",
        });

        if (!yakin) {
          e.target.value = k[f];
          return;
        }
      }

      k[f] = v;
      if (
        [
          "jumlah_kolom",
          "jumlah_baris",
          "jenis_label",
          "label_kustom",
          "arah_baca",
        ].includes(f)
      ) {
        const butuhLabel =
          k.arah_baca === "horizontal" ? k.jumlah_kolom : k.jumlah_baris;
        k.label_baris = buatLabel(k.jenis_label, butuhLabel, k.label_kustom);
        if (f !== "label_kustom" && f !== "nama") k.grid = null;
      }
      if (f === "jenis_label" || f === "arah_baca") {
        renderBagian();
        perbaruiIndikatorSimpan();
        return;
      }
      if (f !== "nama" && f !== "label_kustom") {
        const tag = $(".tag", d);
        if (tag) {
          tag.className = "tag belum";
          tag.textContent = "Belum ditandai";
        }
      }
      kalib.gambar();
      perbaruiIndikatorSimpan();
    };
    d.addEventListener("input", tanganiInput);
    d.addEventListener("change", tanganiInput);
    $("[data-hapus]", d).onclick = async () => {
      const yakin = await tampilModal({
        judul: "Kurangi / Hapus Bagian?",
        pesan: `Apakah Anda yakin ingin menghapus / mengurangi bagian <b>"${escapeHtml(k.nama)}"</b> dari template?`,
        tipe: "danger",
        tombolKonfirmasi: "Ya, Hapus Bagian",
        tombolBatal: "Batal",
        warnaKonfirmasi: "danger",
      });
      if (!yakin) return;
      S.template.kriteria.splice(i, 1);
      if (S.kalibrasi.idx === i) mulaiKalibrasi(-1);
      renderBagian();
      kalib.gambar();
      perbaruiIndikatorSimpan();
    };
    $("[data-tandai]", d).onclick = async () => {
      if (k.grid) {
        const yakin = await tampilModal({
          judul: "Ubah Posisi Bagian?",
          pesan: `Posisi bulatan untuk bagian <b>"${escapeHtml(k.nama)}"</b> sudah ditandai sebelumnya.<br><br>Apakah Anda yakin ingin mengubah posisi bagian ini?`,
          tipe: "warning",
          tombolKonfirmasi: "Ya, Ubah Posisi",
          tombolBatal: "Batal",
        });
        if (!yakin) return;
      }
      mulaiKalibrasi(i);
    };
    w.appendChild(d);
  });
}

/* ---- kalibrasi 2 klik ---- */
function mulaiKalibrasi(i) {
  if (i >= 0) {
    if (!S.template.contohImg) {
      toast("Ambil/unggah lembar contoh dulu.", true);
      return;
    }
    const k = S.template.kriteria[i];
    const butuh =
      k.arah_baca === "horizontal" ? k.jumlah_kolom : k.jumlah_baris;
    if (k.jenis_label !== "kustom") {
      k.label_baris = buatLabel(k.jenis_label, butuh, k.label_kustom);
    } else if (!k.label_baris || k.label_baris.length !== butuh) {
      toast(
        `Jumlah isi bulatan (${(k.label_baris || []).length}) tidak sama dengan jumlah ${k.arah_baca === "horizontal" ? "kolom (kotak ke samping)" : "baris (bulatan ke bawah)"} (${butuh}).`,
        true,
      );
      return;
    }
  }
  S.kalibrasi = { idx: i, klik: [], aktif: i >= 0 };
  renderBagian();
  tampilBantuan();
  kalib.gambar();
}

function tampilBantuan() {
  const b = $("#bantuan-kalibrasi"),
    K = S.kalibrasi;
  if (K.idx < 0) {
    b.innerHTML =
      "Pilih sebuah bagian di kiri, lalu klik <b>Tandai posisi</b>.";
    return;
  }
  const k = S.template.kriteria[K.idx];
  const item1 =
    k.arah_baca === "horizontal" ? "baris/nomor pertama" : "kotak pertama";
  const item2 =
    k.arah_baca === "horizontal"
      ? `baris/nomor ke-${k.jumlah_baris}`
      : `kotak ke-${k.jumlah_kolom}`;
  if (K.klik.length === 0)
    b.innerHTML = `<b>${k.nama}</b> — Langkah 1/2: klik <b>tengah bulatan paling kiri-atas</b> (<b>${k.label_baris[0] || ""}</b> pada ${item1}).`;
  else if (K.klik.length === 1)
    b.innerHTML = `<b>${k.nama}</b> — Langkah 2/2: klik <b>tengah bulatan paling kanan-bawah</b> (<b>${k.label_baris.at(-1) || ""}</b> pada ${item2}).`;
  else
    b.innerHTML = `<b>${k.nama}</b> — Grid sudah pas? <button class="kecil utama" id="ok-kalib">Ya, simpan</button> <button class="kecil" id="ulang-kalib">Ulang</button> &nbsp; <span style="color:#6b7280">Bisa juga seret titik merah untuk menyetel.</span>`;
  const ok = $("#ok-kalib"),
    ul = $("#ulang-kalib");
  if (ok) ok.onclick = simpanKalibrasi;
  if (ul) ul.onclick = () => mulaiKalibrasi(K.idx);
}

function hitungGrid(k, klik) {
  const [a, b] = klik;
  let dx = (b.x - a.x) / Math.max(k.jumlah_kolom - 1, 1);
  let dy = (b.y - a.y) / Math.max(k.jumlah_baris - 1, 1);
  if (k.jumlah_baris === 1) {
    dy = Math.abs(dx) || 10;
  }
  if (k.jumlah_kolom === 1) {
    dx = Math.abs(dy) || 10;
  }
  return {
    x0: a.x,
    y0: a.y,
    dx,
    dy,
  };
}

function simpanKalibrasi() {
  const K = S.kalibrasi;
  if (K.idx < 0 || K.klik.length < 2) return;
  const k = S.template.kriteria[K.idx];
  k.grid = hitungGrid(k, K.klik);
  toast(`"${k.nama}" tersimpan.`);
  const berikut = S.template.kriteria.findIndex((x, i) => i > K.idx && !x.grid);
  S.kalibrasi = { idx: -1, klik: [], aktif: false };
  renderBagian();
  tampilBantuan();
  kalib.gambar();
  perbaruiIndikatorSimpan();
  if (berikut >= 0) mulaiKalibrasi(berikut);
}

let seretTitik = -1;
kalib.onKlik = (x, y) => {
  const K = S.kalibrasi;
  if (!K.aktif) return;
  if (K.klik.length < 2) {
    K.klik.push({ x, y });
    tampilBantuan();
    kalib.gambar();
  }
};

// seret titik merah untuk menyetel halus
$("#kanvas-kalibrasi").addEventListener("mousedown", (e) => {
  const K = S.kalibrasi;
  if (!K.aktif || K.klik.length < 2 || e.button !== 0) return;
  const p = kalib.keGambar(e.offsetX, e.offsetY);
  const tol = 14 / kalib.skala;
  seretTitik = K.klik.findIndex((t) => Math.hypot(t.x - p.x, t.y - p.y) < tol);
  if (seretTitik >= 0) {
    kalib._down = null;
    e.stopPropagation();
  }
});
window.addEventListener("mousemove", (e) => {
  if (seretTitik < 0) return;
  const r = $("#kanvas-kalibrasi").getBoundingClientRect();
  const p = kalib.keGambar(e.clientX - r.left, e.clientY - r.top);
  S.kalibrasi.klik[seretTitik] = p;
  kalib.gambar();
});
window.addEventListener("mouseup", () => {
  seretTitik = -1;
});

/* ---- kaca pembesar ---- */
kalib.onGerak = (x, y, e) => {
  const kEl = kaca.el;
  if (x === null || !S.kalibrasi.aktif || !kalib.img) {
    kEl.style.display = "none";
    return;
  }
  kEl.style.display = "block";
  const ctx = kaca.c.getContext("2d"),
    R = 160,
    zoom = 4,
    sisi = R / zoom;
  ctx.clearRect(0, 0, R, R);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(kalib.img, x - sisi / 2, y - sisi / 2, sisi, sisi, 0, 0, R, R);
  ctx.strokeStyle = "#ff2d55";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(R / 2, 0);
  ctx.lineTo(R / 2, R);
  ctx.moveTo(0, R / 2);
  ctx.lineTo(R, R / 2);
  ctx.stroke();
};

/* ---- overlay grid di kanvas ---- */
kalib.overlay = (ctx, skala) => {
  const T = S.template.kriteria;
  const gambarGrid = (k, grid, warna, tebal, aktif) => {
    ctx.strokeStyle = warna;
    ctx.fillStyle = warna;
    ctx.lineWidth = tebal / skala;
    const stepX = Math.abs(grid.dx);
    const stepY = Math.abs(grid.dy);
    const step =
      k.jumlah_baris === 1
        ? stepX || 10
        : k.jumlah_kolom === 1
          ? stepY || 10
          : Math.min(stepX, stepY);
    const r = Math.max(4, 0.32 * step);
    for (let c = 0; c < k.jumlah_kolom; c++)
      for (let b = 0; b < k.jumlah_baris; b++) {
        const x = grid.x0 + c * grid.dx,
          y = grid.y0 + b * grid.dy;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.stroke();
      }
    if (aktif) return;
    ctx.font = `${Math.max(14, 18 / skala)}px sans-serif`;
    ctx.fillText(k.nama, grid.x0, grid.y0 - step * 0.8);
  };
  T.forEach((k, i) => {
    if (i === S.kalibrasi.idx && S.kalibrasi.klik.length === 2)
      gambarGrid(k, hitungGrid(k, S.kalibrasi.klik), "#00c853", 2, true);
    else if (k.grid && i !== S.kalibrasi.idx)
      gambarGrid(k, k.grid, "#2196f3", 1.5, false);
  });
  S.kalibrasi.klik.forEach((t, i) => {
    ctx.fillStyle = "#ff2d55";
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2 / skala;
    ctx.beginPath();
    ctx.arc(t.x, t.y, 7 / skala, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  });
};

/* ---- ambil lembar contoh ---- */
function setContoh(data) {
  return muatGambar(data.url).then((img) => {
    S.template.contohUrl = data.url;
    S.template.contohImg = img;
    kalib.set(img);
    const el = $("#info-contoh");
    if (data.koreksi === "tidak_terkoreksi") {
      el.className = "info err";
      el.textContent =
        "⚠ Kertas tidak bisa diluruskan otomatis (4 kotak hitam di sudut tidak terbaca). Pastikan seluruh kertas ter-scan lurus dan tidak terpotong.";
    } else {
      el.className = "info ok";
      el.textContent = `✓ Kertas berhasil diluruskan (${data.koreksi}). Sekarang tandai posisi tiap bagian.`;
    }
  });
}

$("#btn-scan-contoh").onclick = async () => {
  const b = $("#btn-scan-contoh");
  b.disabled = true;
  b.textContent = "Memindai...";
  try {
    await setContoh(await kirimJson("/api/contoh/scan", {}));
  } catch (e) {
    toast(e.message, true);
    $("#info-contoh").className = "info err";
    $("#info-contoh").textContent = e.message;
  } finally {
    b.disabled = false;
    b.textContent = "Scan lembar contoh";
  }
};
$("#file-contoh").onchange = async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  try {
    await setContoh(await apiJson("/api/contoh", { method: "POST", body: fd }));
  } catch (er) {
    toast(er.message, true);
  }
  e.target.value = "";
};

$("#btn-tambah-bagian").onclick = async () => {
  if (S.template.kriteria.length > 0) {
    const yakin = await tampilModal({
      judul: "Tambah Bagian Template?",
      pesan: "Apakah Anda yakin ingin menambah bagian baru ke dalam template?",
      tipe: "info",
      tombolKonfirmasi: "Ya, Tambah Bagian",
      tombolBatal: "Batal",
    });
    if (!yakin) return;
  }
  tambahBagian();
  perbaruiIndikatorSimpan();
};

/* ---- simpan / muat template ---- */
async function muatDaftarTemplate() {
  const daftar = await apiJson("/api/template");
  for (const id of ["#pilih-template", "#scan-template"]) {
    const sel = $(id),
      lama = sel.value;
    sel.innerHTML = daftar.length
      ? daftar.map((n) => `<option>${n}</option>`).join("")
      : `<option value="">(belum ada)</option>`;
    if (daftar.includes(lama)) {
      sel.value = lama;
    } else if (daftar.includes("LJK PPTSB")) {
      sel.value = "LJK PPTSB";
    }
  }
}

async function simpanTemplate() {
  const nama = $("#nama-template").value.trim();
  const el = $("#info-template");
  if (!nama) {
    el.className = "info err";
    el.textContent = "Isi nama template dulu.";
    toast("Isi nama template dulu.", true);
    return false;
  }
  if (!S.template.kriteria.length) {
    el.className = "info err";
    el.textContent = "Tambahkan minimal satu bagian.";
    toast("Tambahkan minimal satu bagian.", true);
    return false;
  }
  const belum = S.template.kriteria.filter((k) => !k.grid).map((k) => k.nama);
  if (belum.length) {
    el.className = "info err";
    el.textContent = "Belum ditandai: " + belum.join(", ");
    toast("Ada bagian yang belum ditandai.", true);
    return false;
  }
  const namaKriteria = S.template.kriteria.map((k) => k.nama);
  if (new Set(namaKriteria).size !== namaKriteria.length) {
    el.className = "info err";
    el.textContent = "Nama bagian tidak boleh sama.";
    toast("Nama bagian tidak boleh sama.", true);
    return false;
  }
  for (const k of S.template.kriteria) {
    const butuh =
      k.arah_baca === "horizontal" ? k.jumlah_kolom : k.jumlah_baris;
    if (!k.label_baris || k.label_baris.length !== butuh) {
      if (k.jenis_label !== "kustom") {
        k.label_baris = buatLabel(k.jenis_label, butuh, k.label_kustom);
      } else {
        el.className = "info err";
        el.textContent = `Isi bulatan "${k.nama}" (${(k.label_baris || []).length}) tidak sesuai dengan jumlah ${k.arah_baca === "horizontal" ? "kolom" : "baris"} (${butuh}).`;
        toast(el.textContent, true);
        return false;
      }
    }
  }
  const aman = nama.replace(/[\\/:*?"<>|]/g, "_");
  try {
    await kirimJson("/api/template/" + encodeURIComponent(aman), {
      nama: aman,
      kriteria: S.template.kriteria,
      contoh: S.template.contohUrl,
    });
    el.className = "info ok";
    el.textContent = `✓ Template "${aman}" tersimpan.`;
    await muatDaftarTemplate();
    $("#pilih-template").value = aman;
    $("#scan-template").value = aman;
    catatSnapshotTemplate();
    toast("Template tersimpan");
    return true;
  } catch (err) {
    el.className = "info err";
    el.textContent = "Gagal menyimpan template: " + err.message;
    toast(el.textContent, true);
    return false;
  }
}

$("#btn-simpan-template").onclick = simpanTemplate;

$("#nama-template").addEventListener("input", () => {
  perbaruiIndikatorSimpan();
});

async function muatTemplate(n) {
  if (!n) return;
  const t = await apiJson("/api/template/" + encodeURIComponent(n));
  S.template.kriteria = t.kriteria;
  $("#nama-template").value = n;
  S.kalibrasi = { idx: -1, klik: [], aktif: false };
  renderBagian();
  tampilBantuan();

  const info = $("#info-contoh");
  if (t.contoh) {
    try {
      const img = await muatGambar(t.contoh);
      S.template.contohUrl = t.contoh;
      S.template.contohImg = img;
      kalib.set(img);
      info.className = "info ok";
      info.textContent = "✓ Lembar contoh dari template ini dimuat.";
    } catch (e) {
      S.template.contohUrl = null;
      S.template.contohImg = null;
      kalib.img = null;
      kalib.gambar();
      info.className = "info err";
      info.textContent =
        "Gambar contoh tersimpan tidak ditemukan. Ambil lembar contoh baru bila ingin mengubah posisi bulatan.";
    }
  } else {
    S.template.contohUrl = null;
    S.template.contohImg = null;
    kalib.img = null;
    kalib.gambar();
    info.className = "info";
    info.textContent =
      "Ambil lembar contoh bila ingin melihat/ubah posisi bulatan.";
  }
  catatSnapshotTemplate();
  toast(`Template "${n}" dimuat`);
}

$("#btn-muat-template").onclick = async () => {
  const n = $("#pilih-template").value;
  if (!n) return;
  if (isTemplateDirty()) {
    const yakin = await tampilModal({
      judul: "Muat Template Lain?",
      pesan: `Terdapat perubahan pada template saat ini yang belum disimpan.<br><br>Jika memuat template lain, perubahan tersebut akan hilang. Apakah Anda yakin ingin memuat template <b>"${escapeHtml(n)}"</b>?`,
      tipe: "warning",
      tombolKonfirmasi: "Ya, Muat",
      tombolBatal: "Batal",
    });
    if (!yakin) return;
  }
  await muatTemplate(n);
};

/* ===================== TAB 2: SCAN / UNGGAH ===================== */
function formatWaktuLog() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function mulaiProsesUI(judul, sub = "Menyiapkan...") {
  const box = $("#proses");
  box.hidden = false;
  $("#proses-teks").textContent = judul;
  $("#proses-sub").textContent = sub;

  const bar = $("#proses-bar-fill");
  bar.style.width = "0%";
  bar.classList.remove("indeterminate");

  const list = $("#proses-log-list");
  if (list) list.innerHTML = "";
  const counter = $("#proses-log-counter");
  if (counter) counter.textContent = "0 lembar";

  tambahLogItem(`[${formatWaktuLog()}] Memulai: ${judul}`);
}

function tambahLogItem(pesan, tipe = "info") {
  const list = $("#proses-log-list");
  if (!list) return;
  const item = document.createElement("div");
  item.className = "proses-log-item " + tipe;
  item.textContent = pesan;
  list.appendChild(item);
  list.scrollTop = list.scrollHeight;
}

function perbaruiProsesUI(ev) {
  const judulEl = $("#proses-teks");
  const subEl = $("#proses-sub");
  const bar = $("#proses-bar-fill");
  const counter = $("#proses-log-counter");
  const t = formatWaktuLog();

  if (ev.fase === "scan") {
    if (ev.total && ev.total > 0) {
      judulEl.textContent = `Scanner: Memindai lembar ${ev.saat_ini}/${ev.total}`;
      subEl.textContent = "Sedang memindai... jangan buka penutup scanner.";
      const persen = Math.min(100, Math.round((ev.saat_ini / ev.total) * 100));
      bar.classList.remove("indeterminate");
      bar.style.width = persen + "%";
      if (counter) counter.textContent = `${ev.saat_ini}/${ev.total} lembar`;
    } else {
      judulEl.textContent =
        ev.saat_ini > 0
          ? `Scanner: Berhasil memindai ${ev.saat_ini} lembar`
          : "Scanner: Memindai dari feeder ADF...";
      subEl.textContent = "Mode dinamis (otomatis sampai feeder ADF habis).";
      bar.classList.add("indeterminate");
      if (counter) counter.textContent = `${ev.saat_ini} lembar`;
    }
    tambahLogItem(`[${t}] ${ev.pesan}`, "scan");
  } else if (ev.fase === "scan_selesai") {
    judulEl.textContent = `Scanner Selesai (${ev.saat_ini} lembar)`;
    subEl.textContent = "Menyiapkan pembacaan OMR...";
    bar.classList.remove("indeterminate");
    bar.style.width = "100%";
    if (counter) counter.textContent = `${ev.saat_ini} lembar`;
    tambahLogItem(`[${t}] ✓ ${ev.pesan}`, "scan");
  } else if (ev.fase === "ekstrak") {
    judulEl.textContent = "Mengekstrak berkas unggahan...";
    subEl.textContent = ev.pesan;
    bar.classList.add("indeterminate");
    tambahLogItem(`[${t}] ${ev.pesan}`, "info");
  } else if (ev.fase === "proses") {
    bar.classList.remove("indeterminate");
    if (ev.total && ev.total > 0) {
      const persen = Math.min(100, Math.round((ev.saat_ini / ev.total) * 100));
      judulEl.textContent = `Python: Memproses lembar ${ev.saat_ini}/${ev.total}`;
      subEl.textContent =
        "Meluruskan lembar, deteksi marker, & membaca bulatan OMR.";
      bar.style.width = persen + "%";
      if (counter) counter.textContent = `${ev.saat_ini}/${ev.total} lembar`;
    } else {
      judulEl.textContent = `Python: Memproses lembar ke-${ev.saat_ini}`;
      subEl.textContent = "Membaca bulatan OMR...";
    }
    tambahLogItem(`[${t}] ${ev.pesan}`, "proses");
  } else if (ev.fase === "selesai") {
    judulEl.textContent = "Selesai!";
    subEl.textContent = "Semua lembar berhasil dibaca. Membuka hasil...";
    bar.classList.remove("indeterminate");
    bar.style.width = "100%";
    tambahLogItem(`[${t}] ✓ ${ev.pesan}`, "proses");
  } else {
    judulEl.textContent = ev.pesan || "Memproses...";
    tambahLogItem(`[${t}] ${ev.pesan || ""}`, "info");
  }
}

function selesaiProsesUI() {
  $("#proses").hidden = true;
}

function tampilProses(teks) {
  if (!teks) selesaiProsesUI();
  else mulaiProsesUI(teks);
}

async function bacaStreamSesi(response, onProgress) {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("text/event-stream")) {
    return await response.json();
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let hasilData = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop();

    for (const part of parts) {
      const trimmed = part.trim();
      if (!trimmed) continue;
      for (const line of trimmed.split("\n")) {
        const tr = line.trim();
        if (tr.startsWith("data:")) {
          const raw = tr.substring(5).trim();
          try {
            const ev = JSON.parse(raw);
            if (ev.tipe === "progress") {
              if (onProgress) onProgress(ev);
            } else if (ev.tipe === "selesai") {
              hasilData = ev.data;
            } else if (ev.tipe === "error") {
              throw new Error(ev.pesan || "Terjadi kesalahan saat memproses.");
            }
          } catch (e) {
            if (e.message && !e.message.startsWith("Unexpected token")) {
              throw e;
            }
          }
        }
      }
    }
  }

  if (!hasilData) {
    throw new Error("Proses selesai tanpa mengembalikan data sesi.");
  }
  return hasilData;
}

// Inisialisasi pilihan mode scan (Dinamis vs Manual)
const modeDinamis = $("#mode-scan-dinamis");
const modeManual = $("#mode-scan-manual");
const wadahJumlah = $("#wadah-jumlah-lembar");
const petunjukScan = $("#petunjuk-scan");

if (modeDinamis && modeManual) {
  const updateModeScan = () => {
    if (modeDinamis.checked) {
      if (wadahJumlah) wadahJumlah.style.display = "none";
      if (petunjukScan) {
        petunjukScan.textContent =
          "Letakkan lembar di ADF scanner. Semua lembar di penampung akan dipindai otomatis sampai habis tanpa batas jumlah.";
      }
    } else {
      if (wadahJumlah) wadahJumlah.style.display = "flex";
      if (petunjukScan) {
        petunjukScan.textContent =
          "Letakkan lembar di ADF scanner. Scanner akan memindai tepat sejumlah lembar yang ditentukan.";
      }
    }
  };
  modeDinamis.addEventListener("change", updateModeScan);
  modeManual.addEventListener("change", updateModeScan);
}

async function lanjutKePeriksa(data, namaTemplate) {
  S.sesi = data;
  S.templateSesi = await apiJson(
    "/api/template/" + encodeURIComponent(namaTemplate),
  );
  S.templateNama = namaTemplate;
  S.dipilih = -1;
  S.lembarDipilih = new Set((data.lembar || []).map((l) => l.no));
  renderTabel();
  bukaTab("periksa");
  const n = data.lembar.length,
    cek = data.lembar.filter((l) => l.perlu_cek).length;
  toast(`${n} lembar terbaca` + (cek ? `, ${cek} perlu dicek` : ""));
}

$("#btn-mulai-scan").onclick = async () => {
  const tpl = $("#scan-template").value;
  if (!tpl) {
    $("#info-scan").className = "info err";
    $("#info-scan").textContent = "Pilih template dulu.";
    return;
  }

  const isDinamis = $("#mode-scan-dinamis")
    ? $("#mode-scan-dinamis").checked
    : false;
  let jml = 0;
  if (!isDinamis) {
    jml = parseInt($("#scan-jumlah").value) || 1;
    if (jml < 1) jml = 1;
  }

  $("#info-scan").textContent = "";
  $("#btn-mulai-scan").disabled = true;

  mulaiProsesUI(
    isDinamis
      ? "Menghubungi scanner untuk scan otomatis..."
      : `Memindai ${jml} lembar...`,
    isDinamis
      ? "Mode dinamis (semua lembar di feeder ADF sampai habis)..."
      : "Jangan buka penutup scanner.",
  );

  try {
    const res = await fetch("/api/sesi/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: tpl,
        jumlah: jml,
        dinamis: isDinamis,
        stream: true,
      }),
    });

    const data = await bacaStreamSesi(res, (ev) => {
      perbaruiProsesUI(ev);
    });

    await lanjutKePeriksa(data, tpl);
  } catch (e) {
    $("#info-scan").className = "info err";
    $("#info-scan").textContent = e.message;
    toast(e.message, true);
    tambahLogItem(`[${formatWaktuLog()}] ❌ Gagal: ${e.message}`, "err");
  } finally {
    $("#btn-mulai-scan").disabled = false;
    selesaiProsesUI();
  }
};

async function unggahBanyak(fileList) {
  const tpl = $("#scan-template").value;
  if (!tpl) {
    $("#info-scan").className = "info err";
    $("#info-scan").textContent = "Pilih template dulu.";
    return;
  }
  const files = [...fileList];
  if (!files.length) return;
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));

  $("#info-scan").textContent = "";
  mulaiProsesUI(
    `Membaca ${files.length} berkas unggahan...`,
    "Mengekstrak gambar...",
  );

  try {
    const res = await fetch(
      "/api/sesi/unggah?template=" + encodeURIComponent(tpl) + "&stream=true",
      {
        method: "POST",
        body: fd,
      },
    );

    const data = await bacaStreamSesi(res, (ev) => {
      perbaruiProsesUI(ev);
    });

    await lanjutKePeriksa(data, tpl);
  } catch (e) {
    $("#info-scan").className = "info err";
    $("#info-scan").textContent = e.message;
    toast(e.message, true);
    tambahLogItem(`[${formatWaktuLog()}] ❌ Gagal: ${e.message}`, "err");
  } finally {
    selesaiProsesUI();
  }
}
const dz = $("#dropzone");
["dragenter", "dragover"].forEach((ev) =>
  dz.addEventListener(ev, (e) => {
    e.preventDefault();
    dz.classList.add("hover");
  }),
);
["dragleave", "drop"].forEach((ev) =>
  dz.addEventListener(ev, (e) => {
    e.preventDefault();
    dz.classList.remove("hover");
  }),
);
dz.addEventListener("drop", (e) => unggahBanyak(e.dataTransfer.files));
$("#file-scan").onchange = (e) => {
  unggahBanyak(e.target.files);
  e.target.value = "";
};

/* ===================== TAB 3: PERIKSA ===================== */
const detail = new KanvasGambar($("#kanvas-detail"), $("#wrap-detail"));
$("#dz-in").onclick = () => detail.zoomTengah(1.3);
$("#dz-out").onclick = () => detail.zoomTengah(1 / 1.3);
$("#dz-pas").onclick = () => detail.pas();

function namaBagian() {
  return S.templateSesi ? S.templateSesi.kriteria.map((k) => k.nama) : [];
}
function statusBaris(l) {
  const punyaMasalah =
    l.perlu_cek || Object.values(l.teks).some((t) => t.includes("?"));
  const diedit = Object.values(l.detail).some((d) =>
    d.kolom.some((k) => k.manual),
  );
  return punyaMasalah ? "cek" : diedit ? "edit" : "ok";
}

function updateStatusPilihan() {
  if (!S.sesi || !S.sesi.lembar) return;
  const total = S.sesi.lembar.length;
  const terpilih = S.lembarDipilih ? S.lembarDipilih.size : 0;

  const badge = $("#badge-pilihan-lembar");
  if (badge) {
    badge.textContent = `${terpilih} dari ${total} lembar dipilih`;
    badge.className = "tag " + (terpilih > 0 ? "ok" : "belum");
  }

  const btnKeSimpan = $("#btn-ke-simpan");
  if (btnKeSimpan) {
    btnKeSimpan.textContent = `Lanjut ke Simpan (4) (${terpilih} lembar) →`;
  }

  const cbSemua = $("#cb-semua");
  if (cbSemua) {
    const hanya = $("#hanya-masalah")?.checked;
    const lembarTampil = S.sesi.lembar.filter(
      (l) => !(hanya && statusBaris(l) !== "cek"),
    );
    const jumlahTampilTerpilih = lembarTampil.filter((l) =>
      S.lembarDipilih.has(l.no),
    ).length;

    if (lembarTampil.length === 0 || jumlahTampilTerpilih === 0) {
      cbSemua.checked = false;
      cbSemua.indeterminate = false;
    } else if (jumlahTampilTerpilih === lembarTampil.length) {
      cbSemua.checked = true;
      cbSemua.indeterminate = false;
    } else {
      cbSemua.checked = false;
      cbSemua.indeterminate = true;
    }
  }

  $$("#tabel-hasil tbody tr[data-i]").forEach((tr) => {
    const i = parseInt(tr.dataset.i, 10);
    const l = S.sesi.lembar[i];
    if (l) {
      const dipilih = S.lembarDipilih.has(l.no);
      tr.classList.toggle("tidak-dipilih", !dipilih);
      const cb = tr.querySelector(".cb-lembar");
      if (cb) cb.checked = dipilih;
    }
  });
}

function renderTabel() {
  const t = $("#tabel-hasil"),
    bagian = namaBagian();
  if (!S.sesi) {
    t.innerHTML = "";
    return;
  }
  if (!S.lembarDipilih) {
    S.lembarDipilih = new Set(S.sesi.lembar.map((l) => l.no));
  }
  const hanya = $("#hanya-masalah").checked;
  let h = `<thead><tr>
    <th class="th-cb"><input type="checkbox" id="cb-semua" title="Pilih / Batal Pilih Semua yang Tampil"></th>
    <th>No</th><th>File</th>${bagian.map((b) => `<th>${b}</th>`).join("")}<th>Status</th>
  </tr></thead><tbody>`;
  S.sesi.lembar.forEach((l, i) => {
    const st = statusBaris(l);
    if (hanya && st !== "cek") return;
    const info =
      l.koreksi === "tidak_terkoreksi"
        ? "⚠ tidak lurus"
        : st === "cek"
          ? "perlu dicek"
          : st === "edit"
            ? "dikoreksi"
            : "aman";
    const terpilih = S.lembarDipilih.has(l.no);
    h += `<tr data-i="${i}" class="${st === "cek" ? "cek" : "ok"} ${i === S.dipilih ? "dipilih" : ""} ${!terpilih ? "tidak-dipilih" : ""}">
      <td class="td-cb"><input type="checkbox" class="cb-lembar" data-no="${l.no}" ${terpilih ? "checked" : ""}></td>
      <td>${l.no}</td><td>${l.file}</td>
      ${bagian.map((b) => `<td class="sel-teks ${l.detail[b].kolom.some((k) => k.manual) ? "diedit" : ""}" data-b="${b}">${escapeHtml(l.teks[b] ?? "")}</td>`).join("")}
      <td>${info}</td></tr>`;
  });
  t.innerHTML = h + "</tbody>";
  updateStatusPilihan();
}

$("#hanya-masalah").onchange = renderTabel;

$("#tabel-hasil").addEventListener("change", (e) => {
  if (e.target.matches(".cb-lembar")) {
    const no = parseInt(e.target.dataset.no, 10);
    if (e.target.checked) {
      S.lembarDipilih.add(no);
    } else {
      S.lembarDipilih.delete(no);
    }
    updateStatusPilihan();
  } else if (e.target.id === "cb-semua") {
    const checked = e.target.checked;
    const hanya = $("#hanya-masalah").checked;
    S.sesi.lembar.forEach((l) => {
      const st = statusBaris(l);
      if (hanya && st !== "cek") return;
      if (checked) {
        S.lembarDipilih.add(l.no);
      } else {
        S.lembarDipilih.delete(l.no);
      }
    });
    updateStatusPilihan();
  }
});

$("#tabel-hasil").addEventListener("click", (e) => {
  if (e.target.matches(".cb-lembar")) {
    return;
  }
  const tdCb = e.target.closest(".td-cb");
  if (tdCb) {
    const cb = tdCb.querySelector(".cb-lembar");
    if (cb) {
      cb.checked = !cb.checked;
      cb.dispatchEvent(new Event("change", { bubbles: true }));
    }
    return;
  }
  const tr = e.target.closest("tr[data-i]");
  if (!tr) return;
  const td = e.target.closest("td.sel-teks");
  pilihBaris(parseInt(tr.dataset.i), td ? td.dataset.b : null);
});

$("#btn-pilih-semua").onclick = () => {
  if (!S.sesi || !S.sesi.lembar) return;
  S.sesi.lembar.forEach((l) => S.lembarDipilih.add(l.no));
  updateStatusPilihan();
  toast("Semua lembar dipilih");
};

$("#btn-pilih-aman").onclick = () => {
  if (!S.sesi || !S.sesi.lembar) return;
  S.lembarDipilih.clear();
  S.sesi.lembar.forEach((l) => {
    if (statusBaris(l) !== "cek") {
      S.lembarDipilih.add(l.no);
    }
  });
  updateStatusPilihan();
  toast(`${S.lembarDipilih.size} lembar aman dipilih`);
};

$("#btn-batal-pilih").onclick = () => {
  if (!S.sesi || !S.sesi.lembar) return;
  S.lembarDipilih.clear();
  updateStatusPilihan();
  toast("Pilihan lembar dikosongkan");
};
$("#tabel-hasil").addEventListener("dblclick", (e) => {
  const td = e.target.closest("td.sel-teks");
  if (!td) return;
  editTeks(td);
});

/* ---- edit teks langsung (ketik ulang) ---- */
function editTeks(td) {
  const i = parseInt(td.closest("tr").dataset.i),
    b = td.dataset.b;
  const l = S.sesi.lembar[i],
    k = S.templateSesi.kriteria.find((x) => x.nama === b);
  const input = document.createElement("input");
  input.value = l.teks[b];
  const p = k.arah_baca === "horizontal" ? k.jumlah_baris : k.jumlah_kolom;
  td.textContent = "";
  td.appendChild(input);
  input.focus();
  input.select();
  const selesai = async (simpan) => {
    const nilai = input.value.padEnd(p, "_").slice(0, p);
    if (simpan && nilai !== l.teks[b]) {
      for (let c = 0; c < p; c++) {
        const ch = nilai[c],
          lama = l.detail[b].kolom[c];
        const idx =
          ch === "_" || ch === " "
            ? null
            : k.label_baris.findIndex(
                (x) => x.toLowerCase() === ch.toLowerCase(),
              );
        const sekarang = lama.status === "terisi" ? lama.indeks : null;
        if ((ch === "_" || ch === " ") && sekarang === null) continue;
        if (idx === -1) {
          toast(`Karakter "${ch}" tidak ada di pilihan bagian ${b}`, true);
          continue;
        }
        if (idx !== sekarang || lama.status === "ganda")
          await kirimKoreksi(i, b, c, idx);
      }
    }
    renderTabel();
    if (S.dipilih === i) gambarDetail();
  };
  input.onkeydown = (ev) => {
    if (ev.key === "Enter") selesai(true);
    if (ev.key === "Escape") selesai(false);
  };
  input.onblur = () => selesai(true);
}

async function kirimKoreksi(i, bagian, kolom, indeks) {
  const l = S.sesi.lembar[i];
  const r = await kirimJson("/api/koreksi", {
    template: S.templateNama,
    sesi: S.sesi.sesi,
    no: l.no,
    bagian,
    kolom,
    indeks,
  });
  l.teks[bagian] = r.teks;
  l.detail[bagian] = r.detail;
  l.perlu_cek = statusBarisAsli(l);
}
function statusBarisAsli(l) {
  return (
    l.koreksi === "tidak_terkoreksi" ||
    Object.values(l.detail).some((d) =>
      d.kolom.some((k) => k.status === "ganda"),
    )
  );
}

/* ---- panel detail ---- */
async function pilihBaris(i, bagian) {
  S.dipilih = i;
  $$("#tabel-hasil tr").forEach((tr) =>
    tr.classList.toggle("dipilih", tr.dataset.i == i),
  );
  const l = S.sesi.lembar[i];
  $("#detail-kosong").hidden = true;
  $("#detail").hidden = false;
  $("#detail-judul").textContent = `Lembar ${l.no} · ${l.file}`;
  const sel = $("#detail-bagian");
  sel.innerHTML = namaBagian()
    .map((b) => `<option>${b}</option>`)
    .join("");
  if (bagian) sel.value = bagian;
  const img = await muatGambar(l.lurus);
  detail.set(img);
  gambarDetail();
  setTimeout(() => detail.ukuran(), 30);
}
$("#detail-bagian").onchange = () => {
  gambarDetail();
  fokusBagian();
};

function bagianAktif() {
  return S.templateSesi.kriteria.find(
    (k) => k.nama === $("#detail-bagian").value,
  );
}

function fokusBagian() {
  const k = bagianAktif();
  if (!k || !detail.img) return;
  const g = k.grid,
    w = detail.c.width / detail.dpr,
    h = detail.c.height / detail.dpr;
  const lebar = Math.abs(g.dx) * (k.jumlah_kolom + 1),
    tinggi = Math.abs(g.dy) * (k.jumlah_baris + 1);
  detail.skala = Math.min(w / lebar, h / tinggi) * 0.95;
  detail.ox = w / 2 - (g.x0 + (g.dx * (k.jumlah_kolom - 1)) / 2) * detail.skala;
  detail.oy = h / 2 - (g.y0 + (g.dy * (k.jumlah_baris - 1)) / 2) * detail.skala;
  detail.gambar();
}

function gambarDetail() {
  if (S.dipilih < 0) return;
  const l = S.sesi.lembar[S.dipilih];
  const st = $("#detail-status");
  if (l.koreksi === "tidak_terkoreksi") {
    st.className = "info err";
    st.textContent = "⚠ Kertas tidak diluruskan, hasil bisa meleset.";
  } else {
    const n = Object.values(l.detail)
      .flatMap((d) => d.kolom)
      .filter((k) => k.status === "ganda").length;
    st.className = "info" + (n ? " err" : " ok");
    st.textContent = n
      ? `${n} pilihan ambigu. Klik bulatan yang benar.`
      : "Tidak ada kolom ganda.";
  }

  detail.overlay = (ctx, skala) => {
    const rad = (k) => {
      const stepX = Math.abs(k.grid.dx);
      const stepY = Math.abs(k.grid.dy);
      const step =
        k.jumlah_baris === 1
          ? stepX || 10
          : k.jumlah_kolom === 1
            ? stepY || 10
            : Math.min(stepX, stepY);
      return Math.max(4, 0.3 * step);
    };
    S.templateSesi.kriteria.forEach((k) => {
      const aktif = k.nama === $("#detail-bagian").value,
        g = k.grid,
        r = rad(k);
      const d = l.detail[k.nama];
      const arah = k.arah_baca || "vertikal";

      for (let c = 0; c < k.jumlah_kolom; c++) {
        for (let b = 0; b < k.jumlah_baris; b++) {
          const x = g.x0 + c * g.dx,
            y = g.y0 + b * g.dy;
          const itemIdx = arah === "horizontal" ? b : c;
          const opsiIdx = arah === "horizontal" ? c : b;
          const kol = d.kolom[itemIdx];

          if (kol.status === "terisi" && kol.indeks === opsiIdx) {
            ctx.strokeStyle = kol.manual ? "#2563eb" : "#16a34a";
            ctx.lineWidth = 4 / skala;
            ctx.beginPath();
            ctx.arc(x, y, r * 1.5, 0, 6.283);
            ctx.stroke();
          } else if (kol.status === "ganda" && aktif) {
            ctx.strokeStyle = "#dc2626";
            ctx.lineWidth = 2 / skala;
            ctx.beginPath();
            ctx.arc(x, y, r, 0, 6.283);
            ctx.stroke();
          } else if (aktif) {
            ctx.fillStyle = "rgba(120,120,120,.55)";
            ctx.beginPath();
            ctx.arc(x, y, 2 / skala + 1, 0, 6.283);
            ctx.fill();
          }
        }
      }
      if (aktif) {
        for (let i = 0; i < d.kolom.length; i++) {
          if (d.kolom[i].status === "kosong") {
            if (arah === "horizontal") {
              ctx.fillStyle = "#f59e0b";
              ctx.beginPath();
              ctx.arc(
                g.x0 - Math.abs(g.dx) * 0.9,
                g.y0 + i * g.dy,
                5 / skala + 2,
                0,
                6.283,
              );
              ctx.fill();
            } else {
              ctx.fillStyle = "#f59e0b";
              ctx.beginPath();
              ctx.arc(
                g.x0 + i * g.dx,
                g.y0 - Math.abs(g.dy) * 0.9,
                5 / skala + 2,
                0,
                6.283,
              );
              ctx.fill();
            }
          }
        }
      }
    });
  };
  detail.gambar();
}

detail.onKlik = async (x, y) => {
  if (S.dipilih < 0) return;
  const k = bagianAktif();
  if (!k || !k.grid) return;
  const g = k.grid,
    l = S.sesi.lembar[S.dipilih];
  const c = Math.round((x - g.x0) / (g.dx || 1)),
    b = Math.round((y - g.y0) / (g.dy || 1));
  if (c < 0 || c >= k.jumlah_kolom || b < 0 || b >= k.jumlah_baris) return;
  const px = g.x0 + c * g.dx,
    py = g.y0 + b * g.dy;
  const stepX = Math.abs(g.dx);
  const stepY = Math.abs(g.dy);
  const step =
    k.jumlah_baris === 1
      ? stepX || 10
      : k.jumlah_kolom === 1
        ? stepY || 10
        : Math.min(stepX, stepY);
  if (Math.hypot(x - px, y - py) > 0.65 * step) return;

  const arah = k.arah_baca || "vertikal";
  const itemIdx = arah === "horizontal" ? b : c;
  const opsiIdx = arah === "horizontal" ? c : b;
  const kol = l.detail[k.nama].kolom[itemIdx];
  const indeks =
    kol.status === "terisi" && kol.indeks === opsiIdx ? null : opsiIdx;

  try {
    await kirimKoreksi(S.dipilih, k.nama, itemIdx, indeks);
    renderTabel();
    gambarDetail();
  } catch (e) {
    toast(e.message, true);
  }
};

/* ===================== EKSPOR ===================== */
$("#btn-ekspor").onclick = async () => {
  if (!S.sesi || !S.sesi.lembar) return;
  const lembarEkspor = S.sesi.lembar.filter((l) =>
    S.lembarDipilih ? S.lembarDipilih.has(l.no) : true,
  );
  if (lembarEkspor.length === 0) {
    toast("Pilih minimal 1 lembar untuk diekspor CSV.", true);
    return;
  }
  const bagian = namaBagian();
  const kolom = ["no_urut", "waktu_scan", "nama_file_scan", ...bagian];
  const waktu = new Date().toLocaleString("sv-SE").replace("T", " ");
  const baris = lembarEkspor.map((l) => {
    const o = { no_urut: l.no, waktu_scan: waktu, nama_file_scan: l.file };
    bagian.forEach((b) => (o[b] = l.teks[b]));
    return o;
  });
  try {
    const r = await api("/api/ekspor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kolom, baris }),
    });
    const blob = await r.blob(),
      a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download =
      "hasil_scan_ljk_" +
      new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "") +
      ".csv";
    a.click();
    URL.revokeObjectURL(a.href);
    toast(`CSV (${lembarEkspor.length} lembar) diunduh`);
  } catch (e) {
    toast(e.message, true);
  }
};

/* ===================== TAB 4: SIMPAN & HIT REST API DMR ===================== */
$("#btn-ke-simpan").onclick = () => {
  if (!S.sesi || !S.sesi.lembar || S.sesi.lembar.length === 0) {
    toast("Belum ada data lembar hasil scan.", true);
    return;
  }
  if (!S.lembarDipilih || S.lembarDipilih.size === 0) {
    toast("Pilih minimal 1 lembar pada tabel sebelum lanjut ke Simpan.", true);
    return;
  }
  bukaTab("simpan");
};

const btnKembali = $("#btn-kembali-ke-periksa");
if (btnKembali) {
  btnKembali.onclick = () => bukaTab("periksa");
}

function formatDmrPayload(sesi, templateSesi, lembarDipilih) {
  if (!sesi || !sesi.lembar) return [];

  const kriteria = templateSesi ? templateSesi.kriteria : [];
  const nonSoal = new Set([
    "nama_peserta",
    "nama",
    "nama_siswa",
    "peserta",
    "nomor_peserta",
    "no_peserta",
    "nomor",
    "nis",
    "kode_soal",
    "kode_paket",
    "paket",
    "kode",
    "kelas",
    "jurusan",
    "ruang",
    "tanggal",
    "tgl_lahir",
    "status",
  ]);

  const daftarLembar = sesi.lembar.filter((l) =>
    lembarDipilih ? lembarDipilih.has(l.no) : true,
  );

  return daftarLembar.map((l, idx) => {
    // 1. Nama peserta
    let nama = "";
    if (l.teks["nama_peserta"] !== undefined) nama = l.teks["nama_peserta"];
    else if (l.teks["nama"] !== undefined) nama = l.teks["nama"];
    else if (l.teks["nama_siswa"] !== undefined) nama = l.teks["nama_siswa"];
    else if (l.teks["peserta"] !== undefined) nama = l.teks["peserta"];
    nama = (nama || "").replace(/_+$/, "").trim();
    if (!nama) nama = `PESERTA ${l.no || idx + 1}`;

    // 2. Nomor peserta
    let noPeserta = "";
    if (l.teks["nomor_peserta"] !== undefined) noPeserta = l.teks["nomor_peserta"];
    else if (l.teks["no_peserta"] !== undefined) noPeserta = l.teks["no_peserta"];
    else if (l.teks["nomor"] !== undefined) noPeserta = l.teks["nomor"];
    else if (l.teks["nis"] !== undefined) noPeserta = l.teks["nis"];
    noPeserta = (noPeserta || "").replace(/_+$/, "").trim();
    if (!noPeserta) noPeserta = String(l.no || idx + 1).padStart(4, "0");

    // 3. Kode soal
    let kodeSoal = "";
    if (l.teks["kode_soal"] !== undefined) kodeSoal = l.teks["kode_soal"];
    else if (l.teks["kode_paket"] !== undefined) kodeSoal = l.teks["kode_paket"];
    else if (l.teks["paket"] !== undefined) kodeSoal = l.teks["paket"];
    else if (l.teks["kode"] !== undefined) kodeSoal = l.teks["kode"];
    kodeSoal = (kodeSoal || "").replace(/_+$/, "").trim();
    if (!kodeSoal) kodeSoal = "101";

    // 4. Jawaban all (otomatis pisahkan blok rentang soal misal 1_5, 6_10, 11_15)
    const mapJawaban = new Map();
    const namaKriteriaList =
      kriteria.length > 0
        ? kriteria.map((k) => k.nama)
        : Object.keys(l.teks);

    for (const kName of namaKriteriaList) {
      if (nonSoal.has(kName.toLowerCase())) continue;

      const rawJawaban = String(l.teks[kName] ?? "");

      // Cek apakah format rentang soal, misal: 1_5, 6_10, 11_15, 1-5, soal_1_5, no_1_5, dll.
      const mRange = kName
        .trim()
        .match(
          /^(?:soal|no|nomor|q)?[_\s-]*(\d+)\s*(?:_|-|sd|sampai|to|\.{2,})\s*(\d+)$/i,
        );
      if (mRange) {
        const startNo = parseInt(mRange[1], 10);
        const endNo = parseInt(mRange[2], 10);
        const step = startNo <= endNo ? 1 : -1;
        const count = Math.abs(endNo - startNo) + 1;
        const totalItems = Math.max(count, rawJawaban.length);

        for (let i = 0; i < totalItems; i++) {
          const noSoal = startNo + i * step;
          const ch = i < rawJawaban.length ? rawJawaban[i] : "";
          const jawaban = ch === "_" || ch === " " ? "" : ch.trim();
          if (!mapJawaban.has(noSoal) || (jawaban && !mapJawaban.get(noSoal))) {
            mapJawaban.set(noSoal, jawaban);
          }
        }
        continue;
      }

      // Cek apakah format nomor tunggal, misal: 1, soal_1, no-1, q1, dll.
      const mSingle = kName.trim().match(/^(?:soal|no|nomor|q)?[_\s-]*(\d+)$/i);
      if (mSingle) {
        const startNo = parseInt(mSingle[1], 10);
        if (rawJawaban.length > 1) {
          // Jika jawaban berisi banyak karakter (misal gabungan beberapa soal tanpa format rentang di nama)
          for (let i = 0; i < rawJawaban.length; i++) {
            const noSoal = startNo + i;
            const ch = rawJawaban[i];
            const jawaban = ch === "_" || ch === " " ? "" : ch.trim();
            if (
              !mapJawaban.has(noSoal) ||
              (jawaban && !mapJawaban.get(noSoal))
            ) {
              mapJawaban.set(noSoal, jawaban);
            }
          }
        } else {
          const jawaban =
            rawJawaban === "_" || rawJawaban === " " ? "" : rawJawaban.trim();
          if (
            !mapJawaban.has(startNo) ||
            (jawaban && !mapJawaban.get(startNo))
          ) {
            mapJawaban.set(startNo, jawaban);
          }
        }
        continue;
      }
    }

    const jawabanAll = Array.from(mapJawaban.entries())
      .map(([nomor_soal, jawaban_siswa]) => ({
        nomor_soal,
        jawaban_siswa,
      }))
      .sort((a, b) => a.nomor_soal - b.nomor_soal);

    return {
      no_lembar: l.no,
      nama_peserta: nama,
      nomor_peserta: noPeserta,
      kode_soal: kodeSoal,
      jawaban_all: jawabanAll,
    };
  });
}

function renderTabSimpan() {
  const tanpaSesi = $("#simpan-tanpa-sesi");
  const konten = $("#simpan-konten");
  const lblSesi = $("#label-sesi-aktif");

  if (!S.sesi || !S.sesi.lembar || S.sesi.lembar.length === 0) {
    tanpaSesi.hidden = false;
    konten.hidden = true;
    lblSesi.style.display = "none";
    const theadEl = $("#thead-preview-dmr") || $("#tabel-preview-dmr thead");
    if (theadEl) {
      theadEl.innerHTML = `<tr><th style="text-align:center; width:44px;">No</th><th>Lembar</th><th>Nomor Peserta</th><th>Nama Peserta</th><th style="text-align:center;">Kode Soal</th><th style="text-align:center;">Jml Soal</th><th>Jawaban Siswa</th></tr>`;
    }
    $("#tbody-preview-dmr").innerHTML = "";
    $("#kode-json-preview").textContent = "[]";
    return;
  }

  tanpaSesi.hidden = true;
  konten.hidden = false;
  lblSesi.style.display = "inline-block";
  if (!$("#btn-simpan-kirim").disabled) {
    $("#simpan-proses").hidden = true;
  }

  const totalSemua = S.sesi.lembar.length;
  const terpilihCount = S.lembarDipilih ? S.lembarDipilih.size : totalSemua;
  if (terpilihCount < totalSemua) {
    lblSesi.textContent = `Sesi: ${S.sesi.sesi} (${terpilihCount} dari ${totalSemua} lembar dipilih)`;
  } else {
    lblSesi.textContent = `Sesi: ${S.sesi.sesi} (${terpilihCount} lembar)`;
  }

  const payload = formatDmrPayload(S.sesi, S.templateSesi, S.lembarDipilih);

  // Kartu Info
  $("#simpan-total-peserta").textContent = payload.length;

  const kodeUnik = [...new Set(payload.map((p) => p.kode_soal).filter(Boolean))];
  $("#simpan-kode-soal").textContent = kodeUnik.join(", ") || "-";

  const totalSoal = payload.length > 0 ? payload[0].jawaban_all.length : 0;
  $("#simpan-total-soal").textContent = totalSoal;

  const lembarTerpilihObj = S.sesi.lembar.filter((l) =>
    S.lembarDipilih ? S.lembarDipilih.has(l.no) : true,
  );
  const adaCek = lembarTerpilihObj.some(
    (l) => l.perlu_cek || Object.values(l.teks).some((t) => t.includes("?")),
  );
  const statusEl = $("#simpan-status-data");
  if (payload.length === 0) {
    statusEl.textContent = "0 lembar dipilih";
    statusEl.style.color = "var(--bahaya)";
  } else if (adaCek) {
    statusEl.textContent = "⚠ Perlu dicek";
    statusEl.style.color = "var(--cek)";
  } else {
    statusEl.textContent = "✓ Aman";
    statusEl.style.color = "var(--ok)";
  }

  // Kumpulkan semua nomor soal unik untuk header JAWABAN SISWA
  const daftarSoal = [
    ...new Set(
      payload.flatMap((p) => p.jawaban_all.map((j) => j.nomor_soal)),
    ),
  ].sort((a, b) => a - b);

  // Render Header Tabel Preview
  const theadEl = $("#thead-preview-dmr") || $("#tabel-preview-dmr thead");
  if (theadEl) {
    if (daftarSoal.length > 0) {
      theadEl.innerHTML = `
        <tr>
          <th rowspan="2" style="text-align:center; width:44px;">No</th>
          <th rowspan="2">Lembar</th>
          <th rowspan="2">Nomor Peserta</th>
          <th rowspan="2">Nama Peserta</th>
          <th rowspan="2" style="text-align:center;">Kode Soal</th>
          <th rowspan="2" style="text-align:center;">Jml Soal</th>
          <th colspan="${daftarSoal.length}" class="th-jawaban-utama">JAWABAN SISWA</th>
        </tr>
        <tr>
          ${daftarSoal
            .map((no) => `<th class="th-soal-no">${no}</th>`)
            .join("")}
        </tr>
      `;
    } else {
      theadEl.innerHTML = `
        <tr>
          <th style="text-align:center; width:44px;">No</th>
          <th>Lembar</th>
          <th>Nomor Peserta</th>
          <th>Nama Peserta</th>
          <th>Kode Soal</th>
          <th>Jml Soal</th>
          <th>Jawaban Siswa</th>
        </tr>
      `;
    }
  }

  // Render Preview Table
  let htmlTable = "";
  if (payload.length === 0) {
    const totalCols = 6 + (daftarSoal.length || 1);
    htmlTable = `<tr><td colspan="${totalCols}" style="text-align:center; padding:20px; color:var(--redup);">
      Tidak ada lembar yang dipilih. <button onclick="bukaTab('periksa')" class="kecil" style="margin-left:8px;">Buka Step 3 untuk Pilih Lembar</button>
    </td></tr>`;
  } else {
    payload.forEach((p, idx) => {
      const mapJwb = new Map(
        p.jawaban_all.map((j) => [j.nomor_soal, j.jawaban_siswa]),
      );

      let selJawabanHtml = "";
      if (daftarSoal.length > 0) {
        selJawabanHtml = daftarSoal
          .map((no) => {
            const ans = mapJwb.get(no) ?? "";
            if (ans === "?") {
              return `<td class="td-jawaban-siswa"><span class="tag-ambigu">?</span></td>`;
            } else if (!ans || ans === "_") {
              return `<td class="td-jawaban-siswa"><span class="tag-kosong">_</span></td>`;
            } else {
              return `<td class="td-jawaban-siswa">${escapeHtml(ans)}</td>`;
            }
          })
          .join("");
      } else {
        const ringkasanJawaban = p.jawaban_all
          .map((j) => `${j.nomor_soal}:${j.jawaban_siswa || "_"}`)
          .join(" ");
        selJawabanHtml = `<td class="mono" style="max-width:260px; overflow:hidden; text-overflow:ellipsis;" title="${escapeHtml(ringkasanJawaban)}">${escapeHtml(ringkasanJawaban)}</td>`;
      }

      htmlTable += `<tr>
        <td style="text-align:center;">${idx + 1}</td>
        <td><span class="tag ok" style="font-size:11px; font-weight:600;">Lembar ${p.no_lembar || idx + 1}</span></td>
        <td class="mono font-bold">${escapeHtml(p.nomor_peserta)}</td>
        <td>${escapeHtml(p.nama_peserta)}</td>
        <td style="text-align:center;"><span class="mono">${escapeHtml(p.kode_soal)}</span></td>
        <td style="text-align:center;">${p.jawaban_all.length}</td>
        ${selJawabanHtml}
      </tr>`;
    });
  }
  $("#tbody-preview-dmr").innerHTML = htmlTable;

  // Render JSON Preview
  const cleanPayload = payload.map(({ no_lembar, ...rest }) => rest);
  const jsonStr = JSON.stringify(cleanPayload, null, 2);
  $("#kode-json-preview").textContent = jsonStr;
}

// Tombol Switcher Preview
$("#btn-tab-preview-tabel").onclick = () => {
  $("#btn-tab-preview-tabel").classList.add("aktif");
  $("#btn-tab-preview-json").classList.remove("aktif");
  $("#wrap-preview-tabel").hidden = false;
  $("#wrap-preview-json").hidden = true;
};
$("#btn-tab-preview-json").onclick = () => {
  $("#btn-tab-preview-json").classList.add("aktif");
  $("#btn-tab-preview-tabel").classList.remove("aktif");
  $("#wrap-preview-json").hidden = false;
  $("#wrap-preview-tabel").hidden = true;
};

// Unduh JSON
$("#btn-unduh-json").onclick = () => {
  if (!S.sesi) return;
  const payload = formatDmrPayload(S.sesi, S.templateSesi, S.lembarDipilih);
  if (!payload.length) {
    toast("Tidak ada lembar yang dipilih.", true);
    return;
  }
  const cleanPayload = payload.map(({ no_lembar, ...rest }) => rest);
  const blob = new Blob([JSON.stringify(cleanPayload, null, 2)], {
    type: "application/json",
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `dmr_payload_${S.sesi.sesi || "hasil"}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
  toast(`JSON DMR (${cleanPayload.length} peserta) diunduh`);
};

// Muat Sesi Terakhir
$("#btn-muat-sesi-terakhir").onclick = async () => {
  try {
    const data = await apiJson("/api/sesi/terakhir");
    if (data && data.template) {
      await lanjutKePeriksa(data, data.template);
      bukaTab("simpan");
      toast(`Sesi terakhir (${data.sesi}) dimuat`);
    }
  } catch (e) {
    toast("Gagal memuat sesi terakhir: " + e.message, true);
  }
};

// Simpan & Kirim REST API
$("#btn-simpan-kirim").onclick = async () => {
  if (!S.sesi || !S.sesi.lembar || S.sesi.lembar.length === 0) {
    toast("Tidak ada data hasil scan untuk disimpan.", true);
    return;
  }

  const payload = formatDmrPayload(S.sesi, S.templateSesi, S.lembarDipilih);
  if (!payload.length) {
    toast("Pilih minimal 1 lembar pada tabel untuk disimpan dan diproses.", true);
    return;
  }

  const btnKirim = $("#btn-simpan-kirim");
  const prosesEl = $("#simpan-proses");
  const prosesTeks = $("#simpan-proses-teks");
  const infoEl = $("#info-simpan");
  const blokApi = $("#blok-hasil-api");

  btnKirim.disabled = true;
  prosesEl.hidden = false;
  prosesTeks.textContent = `Menyimpan data (${payload.length} peserta) dan memproses ke REST API…`;
  infoEl.textContent = "";

  try {
    const res = await kirimJson("/api/simpan-dmr", {
      sesi: S.sesi.sesi,
      data: payload,
      lembar_dipilih: payload.map((p) => p.no_lembar),
    });

    infoEl.className = "info " + (res.sukses ? "ok" : "err");
    infoEl.textContent = res.pesan;

    if (res.tersimpan_lokal) {
      $("#info-lokal-simpan").textContent = `✓ Disimpan: data/hasil_simpan/${res.file_simpan} · Gambar lembar: ${res.jumlah_gambar_tersimpan} berkas di hasil_scan_gambar/`;
    }

    if (res.api_response && res.api_response.data) {
      blokApi.hidden = false;
      const apiData = res.api_response;
      $("#badge-api-status").textContent = `HTTP ${res.api_status_code || 201}`;
      $("#badge-api-status").className = "tag ok";
      $("#api-pesan-banner").className = "pesan-banner ok";
      $("#api-pesan-banner").textContent = `${apiData.message || "Berhasil mengolah data DMR"} (${apiData.total_peserta || apiData.data.length} peserta)`;

      let hRows = "";
      apiData.data.forEach((p, idx) => {
        hRows += `<tr>
          <td>${idx + 1}</td>
          <td class="mono font-bold">${escapeHtml(p.nomor_peserta)}</td>
          <td>${escapeHtml(p.nama_peserta)}</td>
          <td><span class="mono">${escapeHtml(p.kode_soal)}</span></td>
          <td>${p.total_soal}</td>
          <td><span class="tag ok">${p.benar}</span></td>
          <td><span class="tag" style="background:#fee2e2; color:#b91c1c;">${p.salah}</span></td>
          <td><span class="tag belum">${p.kosong}</span></td>
          <td><span class="badge-nilai">${p.nilai_total}</span></td>
        </tr>`;
      });
      $("#tbody-hasil-api").innerHTML = hRows;
      toast(res.pesan);
    } else if (res.api_error) {
      blokApi.hidden = false;
      $("#badge-api-status").textContent = res.api_status_code
        ? `HTTP ${res.api_status_code}`
        : "Gagal Kirim API";
      $("#badge-api-status").className = "tag belum";
      $("#api-pesan-banner").className = "pesan-banner err";
      $("#api-pesan-banner").textContent = `Peringatan: ${res.api_error}. Hasil scan tetap aman tersimpan di direktori hasil_scan_gambar/ dan data/hasil_simpan/.`;
      $("#tbody-hasil-api").innerHTML = `<tr><td colspan="9" style="text-align:center; color:var(--redup); padding:16px;">Server REST API tidak memberikan data hasil olah</td></tr>`;
      toast(res.pesan, !res.sukses);
    }
  } catch (err) {
    infoEl.className = "info err";
    infoEl.textContent = "Gagal memproses: " + err.message;
    toast(err.message, true);
  } finally {
    btnKirim.disabled = false;
    prosesEl.hidden = true;
  }
};

/* ===================== INIT ===================== */
(async function init() {
  await muatStatus();
  await muatDaftarTemplate();
  if ($("#pilih-template").value) {
    await muatTemplate($("#pilih-template").value);
  } else {
    tambahBagian({
      nama: "nama_peserta",
      jumlah_kolom: 22,
      jumlah_baris: 26,
      jenis_label: "huruf",
      label_baris: buatLabel("huruf", 26),
    });
    catatSnapshotTemplate();
  }
  tampilBantuan();
})();

window.addEventListener("beforeunload", (e) => {
  if (isTemplateDirty()) {
    e.preventDefault();
    e.returnValue = "";
  }
});

