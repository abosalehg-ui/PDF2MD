/*
 * engine.js — غلاف الخيط العامل: يحوّل رسائله إلى وعود (Promises).
 *
 * الواجهة تتعامل مع محرّك واحد له ثلاث عمليات: إقلاع، وتحويل، وفحص. وكل
 * تفاصيل Pyodide محبوسة خلف هذا الحدّ — من قرأ app.js لا يحتاج أن يعرف أن
 * تحت الصفحة مفسّر بايثون.
 */

const WORKER_URL = new URL('./worker.js', import.meta.url);

/*
 * مهلة حراسة: أطول صمت مسموح به من الخيط قبل أن يُعدّ مفقودًا.
 *
 * الخيط الذي يموت موتًا مفاجئًا — نفاد ذاكرة على ملف ضخم مثلًا — قد لا
 * يُطلق حدث onerror أصلًا، فلا يصل شيء أبدًا ويبقى الوعد معلّقًا إلى
 * الأبد: واجهة تقول «جارٍ التحويل» ولا تتحرّك ولا تُخطئ. المهلة تُعيد
 * ضبطها مع كل رسالة من الخيط، فالصفحة البطيئة لا تُقطع — المقطوع هو
 * الصامت وحده.
 *
 * والقيمة سخيّة عمدًا: المحرّك يبثّ تقدّمه كل خمس صفحات، وخمس صفحات
 * عملاقة داخل WebAssembly قد تطول. والمقايضة في صالح المهلة على كل حال:
 * إنذار كاذب يقول «توقّف الخيط» ويعيد الواجهة للعمل أرحم من تجمّد صامت
 * لا مخرج منه إلا تحديث الصفحة.
 */
export const SILENCE_MS = 180_000;

/** يُرفع حين يُنهي المستخدم العملية — تُعرَض إيقافًا لا فشلًا. */
export class Stopped extends Error {
  constructor() {
    super('أُوقفت العملية بطلب المستخدم.');
    this.name = 'Stopped';
  }
}

export class Engine {
  /**
   * @param {(event: object) => void} listen مستقبِل أحداث التقدّم والسجل
   * @param {{silenceMs?: number}} [opts] مهلة الصمت — تُقصَّر في الاختبار
   */
  constructor(listen, opts = {}) {
    this.listen = listen || (() => {});
    this.silenceMs = opts.silenceMs || SILENCE_MS;
    this.worker = null;
    this.ready = null;
    this.pending = null;
    this.seq = 0;
    this.about = null;
    // هل الوعد `ready` الجاري لم يُحسم بعد؟ لا يصلح `about` بديلًا عنه:
    // فهو يبقى محمّلًا من الإقلاع الأول بعد إنهاء الخيط، فيكذب على الثاني.
    this.booting = false;
    this.timer = null;
  }

  /** يقلع المحرّك، ويرجّع الوعد نفسه إن كان الإقلاع جاريًا. */
  start() {
    if (this.ready) return this.ready;
    this.worker = new Worker(WORKER_URL);
    this.worker.onmessage = (event) => this.#receive(event.data);
    this.worker.onerror = (event) => this.#crash(event.message || 'فشل الخيط العامل');
    this.booting = true;
    this.ready = new Promise((resolve, reject) => {
      this.bootResolve = resolve;
      this.bootReject = reject;
    });
    this.worker.postMessage({ type: 'boot' });
    return this.ready;
  }

  /** يُنهي الخيط الجاري ويُسقط كل ما يشير إليه — استعدادًا لخيط جديد. */
  #discard() {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (this.worker) {
      this.worker.terminate();
      this.worker = null;
    }
    this.ready = null;
    this.booting = false;
  }

  /** يعيد ضبط مهلة الصمت — تُستدعى مع كل إشارة حياة من الخيط. */
  #beat() {
    if (this.timer) clearTimeout(this.timer);
    if (!this.pending) {
      this.timer = null;
      return;
    }
    this.timer = setTimeout(
      () => this.#crash(`انقطع الخيط العامل بلا ردّ لأكثر من ${Math.round(this.silenceMs / 1000)} `
        + 'ثانية — قد يكون الملف أكبر من ذاكرة اللسان.'),
      this.silenceMs,
    );
  }

  get busy() {
    return this.pending !== null;
  }

  /**
   * يشغّل عملية واحدة. لا يُسمح بأكثر من واحدة في الوقت نفسه: المحرّك خيط
   * واحد، وطابور الملفات تديره الواجهة ملفًا ملفًا.
   */
  async run(kind, file, options) {
    await this.start();
    if (this.pending) throw new Error('المحرّك مشغول بعملية أخرى.');

    const id = (this.seq += 1);
    const buffer = await file.arrayBuffer();
    return new Promise((resolve, reject) => {
      this.pending = { id, resolve, reject };
      this.#beat();
      this.worker.postMessage(
        { type: kind, id, name: file.name, data: buffer, options },
        // نقل الملكية لا نسخها: ملف من ٥٠ ميغابايت كان يُنسخ مرة عند
        // الإرسال ومرة عند الكتابة في نظام ملفات المتصفح.
        [buffer],
      );
    });
  }

  convert(file, options) {
    return this.run('convert', file, options);
  }

  diagnose(file) {
    return this.run('diagnose', file, null);
  }

  /**
   * إيقاف فوري: يُنهي الخيط ويُقلع بديلًا في الخلفية.
   *
   * الإقلاع الثاني لا يُنزّل شيئًا — كل ملفات زمن التشغيل في ذاكرة المتصفح
   * المؤقتة بعد الأول — فتكلفته ثوانٍ معدودة، وهي الثمن الوحيد المتاح
   * لمقاطعة بايثون بلا SharedArrayBuffer.
   */
  cancel() {
    if (!this.worker) return;
    this.shutdown();
    this.listen({ type: 'reboot' });
    this.start().catch(() => {});
  }

  /**
   * يُسقط الخيط ومهلته ويرفض المهمة الجارية — بلا إقلاع بديل.
   *
   * `about` يُصفَّر مع الخيط الذي جاء منه: بقاؤه كان يجعل الواجهة تحسب
   * المحرّك جاهزًا بينما بديله لم يُقلع بعد — أو فشل إقلاعه أصلًا.
   */
  shutdown() {
    const pending = this.pending;
    this.pending = null;
    this.about = null;
    this.#discard();
    if (pending) pending.reject(new Stopped());
  }

  /**
   * انهيار قاتل: الخيط لم يعد صالحًا، فيُسقَط ويُرفض كل منتظِر.
   *
   * كان يرفض المهمة الجارية ويترك الخيط الميت مرجَّعًا و`ready` محسومًا،
   * فتُرسَل المهمة التالية إلى خيط لا يردّ ويعلّق وعدها إلى الأبد. وكان
   * الشرط `!this.about` يمنع رفض إقلاعٍ بديل فاشل بعد «إيقاف»، لأن
   * `about` يبقى من الجلسة الأولى. النتيجتان واحدة: صفحة تقول «جاهز»
   * ولا تستجيب، ولا مخرج منها إلا تحديثها.
   */
  #crash(message) {
    const error = new Error(message);
    const pending = this.pending;
    const wasBooting = this.booting;
    this.pending = null;
    this.about = null;
    this.#discard();
    if (wasBooting && this.bootReject) this.bootReject(error);
    if (pending) pending.reject(error);
    this.listen({ type: 'error', fatal: true, msg: message });
  }

  #receive(msg) {
    if (msg.type === 'ready') {
      this.about = msg.about;
      this.booting = false;
      this.listen(msg);
      this.bootResolve(msg.about);
      return;
    }
    if (msg.type === 'result') {
      const pending = this.pending;
      this.pending = null;
      this.#beat();
      if (pending && pending.id === msg.id) pending.resolve(msg.result);
      return;
    }
    if (msg.type === 'error' && msg.fatal) {
      this.#crash(msg.msg);
      return;
    }
    if (msg.type === 'error') {
      const pending = this.pending;
      this.pending = null;
      this.#beat();
      if (pending) pending.reject(new Error(msg.msg));
      return;
    }
    // كل رسالة من الخيط إشارة حياة — التقدّم والسجل معًا
    this.#beat();
    this.listen(msg);
  }
}
