package mathutils

import "testing"

func TestAdd(t *testing.T) {
	if got := Add(2, 3); got != 5 {
		t.Errorf("Add(2, 3) = %d, want 5", got)
	}
}

func TestSubtract(t *testing.T) {
	if got := Subtract(10, 4); got != 6 {
		t.Errorf("Subtract(10, 4) = %d, want 6", got)
	}
}

func TestMultiply(t *testing.T) {
	if got := Multiply(3, 4); got != 12 {
		t.Errorf("Multiply(3, 4) = %d, want 12", got)
	}
}

func TestDivide(t *testing.T) {
	if got := Divide(10, 2); got != 5.0 {
		t.Errorf("Divide(10, 2) = %f, want 5.0", got)
	}
}

func TestDivideByZeroPanics(t *testing.T) {
	defer func() {
		if r := recover(); r == nil {
			t.Error("expected panic on divide by zero")
		}
	}()
	Divide(1, 0)
}
