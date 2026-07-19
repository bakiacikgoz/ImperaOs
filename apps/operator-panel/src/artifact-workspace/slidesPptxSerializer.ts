import PptxGenJS from 'pptxgenjs';

import { SlidesArtifactContentSchema, type SlidesArtifactContent } from './artifactContracts';

function tableText(value: string | number | boolean | null): string {
  if (value === null) return '';
  return typeof value === 'boolean' ? (value ? 'true' : 'false') : String(value);
}

export type SlidesPptxAsset = { dataUrl: string; sha256: string };

export async function serializeSlidesPptx(
  value: unknown,
  assets: Readonly<Record<string, SlidesPptxAsset>> = {},
): Promise<Uint8Array> {
  const content = SlidesArtifactContentSchema.parse(value);
  const pptx = new PptxGenJS();
  pptx.layout = 'LAYOUT_WIDE';
  pptx.author = 'ImperaOS';
  pptx.company = 'ImperaOS';
  pptx.subject = 'Governed artifact export';
  pptx.title = 'ImperaOS artifact slides';
  pptx.theme = {
    headFontFace: 'Aptos Display', bodyFontFace: 'Aptos',
  };

  content.slides.forEach((source) => {
    const slide = pptx.addSlide();
    slide.background = { color: content.theme.backgroundColor };
    source.elements.forEach((element) => {
      const position = { x: element.x, y: element.y, w: element.width, h: element.height };
      if (element.type === 'text') {
        slide.addText(element.text, {
          ...position, fontFace: 'Aptos', fontSize: element.fontSize,
          color: element.color ?? content.theme.foregroundColor, bold: element.bold,
          margin: 0.05, breakLine: false, fit: 'shrink',
        });
      } else if (element.type === 'shape') {
        slide.addShape(
          element.shape === 'ellipse' ? pptx.ShapeType.ellipse : pptx.ShapeType.rect,
          { ...position, fill: { color: element.fillColor }, line: { color: element.lineColor } },
        );
      } else if (element.type === 'line') {
        slide.addShape(pptx.ShapeType.line, {
          ...position, line: { color: element.color, width: element.lineWidth },
        });
      } else if (element.type === 'table') {
        slide.addTable(element.rows.map((row) => row.map((cell) => ({ text: tableText(cell) }))), {
          ...position, border: { color: content.theme.foregroundColor, pt: 1 },
          color: content.theme.foregroundColor, fill: { color: content.theme.backgroundColor },
          fontFace: 'Aptos', fontSize: 12, margin: 0.04,
        });
      } else if (element.type === 'chart') {
        slide.addChart(
          pptx.ChartType[element.chartType],
          element.series.map((series) => ({
            name: series.name, labels: element.categories, values: series.values,
          })),
          { ...position, showLegend: true, showTitle: false, showValue: false },
        );
      } else {
        const asset = assets[element.assetId];
        if (!asset) throw new Error(`Slide image asset is unavailable: ${element.assetId}`);
        slide.addImage({
          ...position,
          data: asset.dataUrl,
          altText: element.altText,
          transparency: 0,
        });
      }
    });
  });

  const output = await pptx.write({ outputType: 'uint8array', compression: false });
  return output instanceof Uint8Array ? output : new Uint8Array(output as ArrayBuffer);
}

export type SlidesPptxSerializeRequest = {
  content: SlidesArtifactContent;
  assets: Record<string, SlidesPptxAsset>;
};
