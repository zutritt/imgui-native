export class BoolRef {
  constructor();
  constructor(value: boolean);

  value: boolean;
}

export class IntRef {
  constructor();
  constructor(value: number);

  value: number;
}

export class FloatRef {
  constructor();
  constructor(value: number);

  value: number;
}

export class DoubleRef {
  constructor();
  constructor(value: number);

  value: number;
}

export class StringRef {
  constructor();
  constructor(value: string);

  value: string;

  resize(newCapacity: number | bigint): void;
}

export class StringListRef {
  constructor();
  constructor(values: string[]);

  readonly count: number;

  update(values: string[]): void;
}

export class CallbackRef<CallbackType extends (...args: unknown[]) => unknown> {
  constructor(callback: CallbackType);
}
