import { describe, expect, test } from 'bun:test';
import im from '../src/index.js';

describe('core', () => {
  test('loads native addon', () => {
    expect(im).toBeDefined();
    expect(typeof im).toBe('object');
    expect(Object.keys(im).length).toBeGreaterThan(100);
  });

  test('context lifecycle', () => {
    const ctx = im.createContext();
    expect(ctx).toBeDefined();
    im.destroyContext(ctx);
  });

  test('value and ref wrappers', () => {
    const v = new im.Vec2(3.5, 7.25);
    expect(v.x).toBeCloseTo(3.5);
    expect(v.y).toBeCloseTo(7.25);

    const b = new im.BoolRef(true);
    b.value = false;
    expect(b.value).toBe(false);

    const n = new im.IntRef(42);
    n.value = 7;
    expect(n.value).toBe(7);

    const s = new im.StringRef('hello');
    s.value = 'world';
    expect(s.value).toBe('world');
  });

  test('font atlas data helpers', () => {
    const ctx = im.createContext();
    const atlas = im.getIO().fonts;

    atlas.addFontDefault();

    const a8 = atlas.getTexDataAsAlpha8();
    expect(a8.width).toBeGreaterThan(0);
    expect(a8.height).toBeGreaterThan(0);
    expect(a8.pixels).toBeInstanceOf(Uint8Array);

    const rgba = atlas.getTexDataAsRGBA32();
    expect(rgba.width).toBeGreaterThan(0);
    expect(rgba.height).toBeGreaterThan(0);
    expect(rgba.pixels).toBeInstanceOf(Uint8Array);
    expect(rgba.pixels.length).toBe(rgba.width * rgba.height * 4);

    im.destroyContext(ctx);
  });

  test('callback bridge', () => {
    let received = null;
    const ref = new im.CallbackRef((value) => {
      received = value;
    });

    im.setCallback(ref);
    im.callCallback();

    expect(received).toBe(42);
  });
});
