# Copy here code of line function from previous exercise and use it in your solution
def character(number, word_input):
    if len(word_input) == 0:
        character = "*"
    else:
        character = word_input[0]
    if character == " ":
        character = "*"

    print(character * number)

#triangle section
def triangle(size, char):
    # Prints a triangle where each line has more characters than the previous
    # Example: size=3 should print:
    # x
    # xx
    # xxx
    index = 0
    while index < size:
        # ORIGINAL BUG: was passing "character" (a string literal) instead of actual char parameter
        # NEW: now passes the actual character parameter (e.g., "x", "-", etc.)
        character(index + 1, char)
        index += 1
#rectangle section
def box_of_hashes(height, width, char):
    # Prints a filled rectangle with 'height' rows and 'width' columns of the given character
    # Example: height=2, width=3, char='o' should print:
    # ooo
    # ooo
    index = 0
    while index < height:
        # ORIGINAL BUG #1: function only took 'height' parameter, not 'width'
        # ORIGINAL BUG #2: was passing "character" (a string literal) instead of actual char parameter
        # ORIGINAL BUG #3: was using 'height' for the width (character count per row) instead of separate 'width'
        # NEW: now passes width (how many characters per row) and actual char parameter
        character(width, char)
        index += 1
#shape section
def shape(size, character1, height, character2):
    # Combines a triangle and a rectangle to make a shape
    # Parameters:
    #   size: height of triangle (and width of rectangle)
    #   character1: what character to use for the triangle (e.g., "x")
    #   height: how many rows for the rectangle bottom
    #   character2: what character to use for the rectangle (e.g., "o")
    
    # ORIGINAL BUG #1: triangle() was called with only 'size', not passing 'character1'
    # NEW: now passes character1 so triangle uses the right character
    triangle(size, character1)
    
    # ORIGINAL BUG #2: box_of_hashes() was called with only 'height', missing 'width' and 'character2'
    # NEW: now passes width (size) and character2 so rectangle uses the right character and width
    box_of_hashes(height, size, character2)
# You can test your function by calling it within the following block
if __name__ == "__main__":
    shape(5, "x", 2, "o")