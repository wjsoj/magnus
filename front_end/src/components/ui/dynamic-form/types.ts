// front_end/src/components/ui/dynamic-form/types.ts

export type FieldType = "text" | "number" | "boolean" | "select";

export interface FieldOption {
  label: string;
  value: string | number;
  description?: string;
}

export interface FieldSchema {
  key: string;
  label: string;
  type: FieldType;
  default?: any;
  description?: string;
  scope?: string | null;

  // Int specific
  min?: number;
  max?: number;
  step?: number;

  // Str specific
  placeholder?: string;
  multi_line?: boolean;
  color?: string;
  border_color?: string;

  // Select/Literal specific
  options?: FieldOption[];
}