import { serializeSlidesPptx, type SlidesPptxSerializeRequest } from './slidesPptxSerializer';

self.onmessage = async (event: MessageEvent<SlidesPptxSerializeRequest>) => {
  try {
    const bytes = await serializeSlidesPptx(event.data.content, event.data.assets);
    self.postMessage({ ok: true, bytes }, { transfer: [bytes.buffer] });
  } catch {
    self.postMessage({ ok: false, error: 'Slides PPTX serialization failed safely.' });
  }
};
