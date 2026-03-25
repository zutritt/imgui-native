import imgui from './src'

const ref = new imgui.CallbackRef((data) => {
  console.log('[JS] Callback called with data:', data)
});

console.log(ref)

console.log('[JS] Setting callback')
imgui.setCallback(ref)

console.log('[JS] Calling callback')
imgui.callCallback()
