import { describe, expect, test } from 'bun:test';
import im from '../src/index.js';

describe('backend namespaces', () => {
  test('exports v1 backend namespaces', () => {
    const expected = [
      'ImplGlfw',
      'ImplGlfw3',
      'ImplOpenGL2',
      'ImplOpenGL3',
      'ImplSDL2',
      'ImplSDL3',
    ];

    for (const name of expected) {
      expect(im[name]).toBeDefined();
      expect(typeof im[name]).toBe('object');
    }
  });

  test('does not export out-of-scope renderer namespaces for v1', () => {
    expect(im.ImplSDLRenderer2).toBeUndefined();
    expect(im.ImplSDLRenderer3).toBeUndefined();
  });

  test('glfw3 is an alias of glfw', () => {
    expect(im.ImplGlfw3).toBe(im.ImplGlfw);
  });

  test('backend namespaces expose expected method shapes', () => {
    expect(typeof im.ImplGlfw.initForOpenGL).toBe('function');
    expect(typeof im.ImplGlfw.shutdown).toBe('function');
    expect(typeof im.ImplOpenGL3.init).toBe('function');
    expect(typeof im.ImplOpenGL3.renderDrawData).toBe('function');

    // Optional backends are always exported; they may be real or stubs.
    expect(typeof im.ImplOpenGL2.shutdown).toBe('function');
    expect(typeof im.ImplSDL2.shutdown).toBe('function');
    expect(typeof im.ImplSDL3.shutdown).toBe('function');
  });
});
