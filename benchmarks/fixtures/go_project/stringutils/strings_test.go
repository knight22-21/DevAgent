package stringutils

import "testing"

func TestReverse(t *testing.T) {
	if got := Reverse("hello"); got != "olleh" {
		t.Errorf("Reverse(%q) = %q, want %q", "hello", got, "olleh")
	}
}

func TestCountWords(t *testing.T) {
	if got := CountWords("hello world foo"); got != 3 {
		t.Errorf("CountWords(%q) = %d, want 3", "hello world foo", got)
	}
}

func TestTitleCase(t *testing.T) {
	cases := [][2]string{
		{"hello world", "Hello World"},
		{"foo bar baz", "Foo Bar Baz"},
		{"go is great", "Go Is Great"},
	}
	for _, c := range cases {
		got := TitleCase(c[0])
		if got != c[1] {
			t.Errorf("TitleCase(%q) = %q, want %q", c[0], got, c[1])
		}
	}
}
