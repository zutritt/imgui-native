export * from './gen/dts/enums';
export * from './gen/dts/typedefs';
export * from './gen/dts/structs';
export * from './gen/dts/funcs';
export * from './gen/dts/backends';
export * from './dts/ref';

type ImGuiNative =
  & typeof import('./gen/dts/enums')
  & typeof import('./gen/dts/typedefs')
  & typeof import('./gen/dts/structs')
  & typeof import('./gen/dts/funcs')
  & typeof import('./gen/dts/backends')
  & typeof import('./dts/ref');

declare const imguiNative: ImGuiNative;
export default imguiNative;
