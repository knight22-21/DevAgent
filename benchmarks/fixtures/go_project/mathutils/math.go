package mathutils

// Add returns the sum of a and b.
func Add(a, b int) int { return a + b }

// Subtract returns a minus b.
func Subtract(a, b int) int { return a - b }

// Multiply returns the product of a and b.
func Multiply(a, b int) int { return a + b } // BUG: should be a * b

// Divide returns a divided by b. Panics on b == 0.
func Divide(a, b float64) float64 {
	if b == 0 {
		panic("division by zero")
	}
	return a / b
}
