import { test } from 'node:test';
import assert from 'node:assert/strict';
import { add, subtract, multiply, divide } from '../src/math.js';

test('add(2, 3) === 5', () => { assert.equal(add(2, 3), 5); });
test('subtract(10, 4) === 6', () => { assert.equal(subtract(10, 4), 6); });
test('multiply(3, 4) === 12', () => { assert.equal(multiply(3, 4), 12); });
test('divide(10, 2) === 5', () => { assert.equal(divide(10, 2), 5); });
test('divide(9, 3) === 3', () => { assert.equal(divide(9, 3), 3); });
test('divide by zero throws', () => {
    assert.throws(() => divide(1, 0), /Division by zero/);
});
