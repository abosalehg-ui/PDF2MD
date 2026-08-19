/*
 * engine.js — غلاف الخيط العامل: يحوّل رسائله إلى وعود (Promises).
 *
 * الواجهة تتعامل مع محرّك واحد له ثلاث عمليات: إقلاع، وتحويل، وفحص. وكل
 * تفاصيل Pyodide محبوسة خلف هذا الحدّ — من قرأ app.js لا يحتاج أن يعرف أن
 * تحت الصفحة مفسّر بايثون.
 */

const WORKER_URL = new URL('./worker.js', import.meta.url);

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
   */
  constructor(listen) {
    this.listen = listen || (() => {});
    this.worker = null;
    this.ready = null;
    this.pending = null;
    this.seq = 0;
    this.about = null;
  }

  /** يقلع المحرّك، ويرجّع الوعد نفسه إن كان الإقلاع جاريًا. */
  start() {
    if (this.ready) return this.ready;
    this.worker = new Worker(WORKER_URL);
    this.worker.onmessage = (event) => this.#receive(event.data);
    this.worker.onerror = (event) => this.#crash(event.message || 'فشل الخيط العامل');
    this.ready = new Promise((resolve, reject) => {
      this.bootResolve = resolve;
      this.bootReject = reject;
    });
    this.worker.postMessage({ type: 'boot' });
    return this.ready;
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
    const pending = this.pending;
    this.worker.terminate();
    this.worker = null;
    this.ready = null;
    this.pending = null;
    if (pending) pending.reject(new Stopped());
    this.listen({ type: 'reboot' });
    this.start().catch(() => {});
  }

  #crash(message) {
    const error = new Error(message);
    if (this.bootReject && !this.about) this.bootReject(error);
    if (this.pending) {
      this.pending.reject(error);
      this.pending = null;
    }
    this.listen({ type: 'error', fatal: true, msg: message });
  }

  #receive(msg) {
    if (msg.type === 'ready') {
      this.about = msg.about;
      this.listen(msg);
      this.bootResolve(msg.about);
      return;
    }
    if (msg.type === 'result') {
      const pending = this.pending;
      this.pending = null;
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
      if (pending) pending.reject(new Error(msg.msg));
      return;
    }
    this.listen(msg);
  }
}
