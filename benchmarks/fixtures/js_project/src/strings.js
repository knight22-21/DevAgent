// strings.js — string utilities

export function reverse(s) {
    return s.split('').reverse().join('');
}

export function countWords(s) {
    return s.trim().split(/\s+/).filter(Boolean).length;
}

export function capitalize(s) {
    return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}

// camelCase(s) is missing — add it
// It should convert "hello world foo" -> "helloWorldFoo"
