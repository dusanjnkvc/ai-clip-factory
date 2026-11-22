/** Rasterize uploaded images before storage. SVG support is an intentionally
 * small geometric subset: no scripts, links, styles, foreignObject or images. */
export async function prepareEditorImage(file: File): Promise<File> {
  if (file.size > 15 * 1024 * 1024)
    throw new Error("Images must be at most 15 MB.");
  let blob: Blob = file;
  if (/\.svg$/i.test(file.name)) {
    const xml=await file.text();
    if(/<!DOCTYPE|<!ENTITY/i.test(xml))throw new Error('SVG document types and entities are unsupported. Export a transparent PNG.');
    const doc = new DOMParser().parseFromString(
      xml,
      "image/svg+xml",
    );
    if (
      doc.querySelector("parsererror") ||
      doc.documentElement.localName !== "svg"
    )
      throw new Error("Invalid SVG.");
    const tags = new Set([
      "svg",
      "g",
      "path",
      "rect",
      "circle",
      "ellipse",
      "line",
      "polyline",
      "polygon",
    ]);
    const attrs = new Set([
      "xmlns",
      "viewBox",
      "width",
      "height",
      "x",
      "y",
      "x1",
      "y1",
      "x2",
      "y2",
      "cx",
      "cy",
      "r",
      "rx",
      "ry",
      "d",
      "points",
      "fill",
      "stroke",
      "stroke-width",
      "opacity",
      "fill-opacity",
      "stroke-opacity",
      "fill-rule",
      "transform",
    ]);
    let count = 0;
    for (const el of [
      doc.documentElement,
      ...Array.from(doc.documentElement.querySelectorAll("*")),
    ]) {
      if (
        ++count > 2000 ||
        !tags.has(el.localName) ||
        el.namespaceURI !== "http://www.w3.org/2000/svg"
      )
        throw new Error(
          "Use a simple geometric SVG, or export a transparent PNG.",
        );
      for (const attr of Array.from(el.attributes)) {
        if (
          attr.name === "xmlns" &&
          attr.value === "http://www.w3.org/2000/svg"
        )
          continue;
        if (
          !attrs.has(attr.name) ||
          /url\s*\(|https?:|data:|javascript:|[<>]/i.test(attr.value)
        )
          throw new Error(
            "SVG contains unsupported or external content. Export it as PNG.",
          );
      }
    }
    blob = new Blob([new XMLSerializer().serializeToString(doc)], {
      type: "image/svg+xml",
    });
  } else if (!/\.(png|jpe?g|webp)$/i.test(file.name))
    throw new Error("Choose PNG, JPEG, WebP or a simple SVG.");
  const url = URL.createObjectURL(blob);
  try {
    const img = new Image();
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error("Image decoding timed out.")),
        15000,
      );
      img.onload = () => {
        clearTimeout(timer);
        resolve();
      };
      img.onerror = () => {
        clearTimeout(timer);
        reject(new Error("This image cannot be decoded."));
      };
      img.src = url;
    });
    if (!img.width || !img.height || img.width * img.height > 16_000_000)
      throw new Error("Use an image with at most 16 million pixels.");
    const scale = Math.min(1, 2048 / img.width, 2048 / img.height),
      canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(img.width * scale));
    canvas.height = Math.max(1, Math.round(img.height * scale));
    canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height);
    const png = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (value) =>
          value
            ? resolve(value)
            : reject(new Error("Image conversion failed.")),
        "image/png",
      ),
    );
    return new File([png], file.name.replace(/\.[^.]+$/, ".png"), {
      type: "image/png",
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}
