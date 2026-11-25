/* The Qt WebChannel transport. call() returns a promise for every request;
 * on() subscribes to pushed events ("state", "log", "notice"). */
(() => {
  'use strict';
  let native = null;
  let sequence = 0;
  const pending = new Map();
  const listeners = new Map();

  function connect() {
    return new Promise((resolve, reject) => {
      if (!window.qt?.webChannelTransport) {
        reject(new Error('Bandar must run inside its desktop window.'));
        return;
      }
      new QWebChannel(qt.webChannelTransport, (channel) => {
        native = channel.objects.native;
        native.reply.connect(receiveReply);
        native.event.connect(receiveEvent);
        resolve(JSON.parse(native.appInfo));
      });
    });
  }

  function receiveReply(text) {
    const { id, result } = JSON.parse(text);
    const resolve = pending.get(id);
    if (!resolve) return;
    pending.delete(id);
    resolve(result);
  }

  function receiveEvent(text) {
    const event = JSON.parse(text);
    for (const listener of listeners.get(event.type) || []) {
      try {
        listener(event);
      } catch (error) {
        console.error(error);
      }
    }
  }

  function call(method, params = {}) {
    const id = ++sequence;
    return new Promise((resolve) => {
      pending.set(id, resolve);
      native.request(JSON.stringify({ id, method, params }));
    });
  }

  function on(type, listener) {
    if (!listeners.has(type)) listeners.set(type, []);
    listeners.get(type).push(listener);
  }

  window.Native = { connect, call, on };
})();
