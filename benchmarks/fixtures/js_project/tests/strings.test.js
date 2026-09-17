import { test } from 'node:test';
import assert from 'node:assert/strict';
import { reverse, countWords, capitalize, camelCase } from '../src/strings.js';

test('reverse("hello") === "olleh"', () => { assert.equal(reverse('hello'), 'olleh'); });
test('countWords("hello world") === 2', () => { assert.equal(countWords('hello world'), 2); });
test('capitalize("hello") === "Hello"', () => { assert.equal(capitalize('hello'), 'Hello'); });
test('camelCase("hello world") === "helloWorld"', () => {
    assert.equal(camelCase('hello world'), 'helloWorld');
});
test('camelCase("foo bar baz") === "fooBarBaz"', () => {
    assert.equal(camelCase('foo bar baz'), 'fooBarBaz');
});
