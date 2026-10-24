import offthemes
import ansicat


# Empty
def test_render_table_empty(mocker):
    content = r"""
<table>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """++
++
"""

# Empty
def test_render_table_empty2(mocker):
    content = r"""
<table>
  <thead>
  </thead>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """++
++
"""

# Empty
def test_render_table_empty3(mocker):
    content = r"""
<table>
  <thead>
  </thead>
  <tbody>
  </tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """++
++
"""

# Empty
def test_render_table_empty4(mocker):
    content = r"""
<table>
  <thead>
  </thead>
  <tbody>
    <tr></tr>
  </tbody>
  <tfoot>
  </tfoot>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """++
++
"""

# Single cell
def test_render_table_empty4(mocker):
    content = r"""
<table>
  <thead>
  </thead>
  <tbody>
    <tr><td><td></tr>
  </tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+--+
|  |
+--+
"""


# Varying widths, should pad to longest
def test_render_table(mocker):
    content = r"""
<table>
    <thead>
    <tr><th>col1</th></tr>
    </thead>
    <tbody>
    <tr><td>v1</td></tr>
    <tr><td>widest</td></tr>
    <tr><td>v3</td></tr>
    </tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+--------+
| col1   |
+--------+
| v1     |
| widest |
| v3     |
+--------+
"""

# Varying widths, inline (offline) img
# note assumes the image can be rendered via a plugin (but need no external file/cache)
def test_render_table_img1(mocker):
    content = r"""
<table>
    <thead>
    <tr><th>col1</th></tr>
    </thead>
    <tbody>
    <tr><td>v1</td></tr>
    <tr><td>widest</td></tr>
    <tr><td><img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAAABlBMVEX///+/v7+jQ3Y5AAAADklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5CYII="/></td></tr>
    </tbody>
</table>"""
    # note: we need to pass a url for the image caching to work
    toreturn = ansicat.set_renderer(content, "http://test_render_table_img1", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    if ansicat.RENDER_IMAGE_IN_TABLE:
        assert r == """+----------------------------------------------+
| col1                                         |
+----------------------------------------------+
| v1                                           |
| widest                                       |
|                                              |
|                                     \x1b[?25l\x1b[48;2;191;191;191m    \x1b[48;2;255;255;255m    \x1b[0m |
|                                     \x1b[48;2;191;191;191m    \x1b[48;2;255;255;255m    \x1b[0m |
|                                     \x1b[48;2;255;255;255m    \x1b[48;2;191;191;191m    \x1b[0m |
|                                     \x1b[48;2;255;255;255m    \x1b[48;2;191;191;191m    \x1b[0m |
|                                     \x1b[?25h         |
|                                              |
| \x1b[33;2m[IMG] [1]\x1b[39;22m                                    |
+----------------------------------------------+
"""
    else:
      assert r == """+-----------+
| col1      |
+-----------+
| v1        |
| widest    |
| \x1b[33;2m[IMG] [1]\x1b[39;22m |
+-----------+
"""

# Varying row groups
def test_render_table_row_groups1(mocker):
    content = r"""
<table>
    <thead>
    <tr><th>col1</th></tr>
    </thead>
    <tbody>
    <tr><td>v1</td></tr>
    </tbody>
    <tr><td>float</td></tr>
    <thead>
    <tr><th>col2</th></tr>
    </thead>
    <tbody>
    <tr><td>widest</td></tr>
    </tbody>
    <tfoot>
    <tr><td>footer</td></tr>
    </tfoot>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+--------+
| col1   |
+--------+
| v1     |
+--------+
| float  |
+--------+
| col2   |
+--------+
| widest |
+--------+
| footer |
+--------+
"""

# Varying row groups with different alignments
def test_render_table_row_groups2(mocker):
    content = r"""
<table>
    <thead>
    <tr><th>col1</th></tr>
    </thead>
    <tbody>
    <tr><td>3</td></tr>
    <tr><td>14</td></tr>
    </tbody>
    <tr><td>float</td></tr>
    <thead>
    <tr><th>col2</th></tr>
    </thead>
    <tbody>
    <tr><td>widest</td></tr>
    </tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+--------+
| col1   |
+--------+
|      3 |
|     14 |
+--------+
| float  |
+--------+
| col2   |
+--------+
| widest |
+--------+
"""

# Rendering of cell contents
def test_render_table_color(mocker):
    content = r"""
<table>
    <thead>
    <tr><th>col1</th></tr>
    </thead>
    <tbody>
    <tr><td>v1</td></tr>
    <tr><td><em>widest</em></td></tr>
    <tr><td>v3</td></tr>
    </tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+--------+
| col1   |
+--------+
| v1     |
| \x1b[3mwidest\x1b[23m |
| v3     |
+--------+
"""

# Two columns
def test_render_table_two_cols(mocker):
    content = r"""
<table>
    <thead>
    <tr><th>col1</th><th>col2</th></tr>
    </thead>
    <tbody>
    <tr><td>v1</td><td>v2</td></tr>
    <tr><td>widest</td><td>v4</td></tr>
    <tr><td>v5</td><td>v6</td></tr>
    </tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+--------+------+
| col1   | col2 |
+--------+------+
| v1     | v2   |
| widest | v4   |
| v5     | v6   |
+--------+------+
"""

# Two columns, no sections, one is numeric (except th 1st row = implied head) and should auto align to the right
def test_render_table_two_cols_no_sections(mocker):
    content = r"""
<table>
    <tr><th>col1</th><th>col2</th></tr>
    <tr><td>v1</td><td>100</td></tr>
    <tr><td>widest</td><td>4</td></tr>
    <tr><td>v5</td><td>60</td></tr>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+--------+------+
| col1   | col2 |
| v1     | 100  |
| widest | 4    |
| v5     | 60   |
+--------+------+
"""

# Three columns, one is numeric (except thead) and should auto align to the right
def test_render_table_three_cols(mocker):
    content = r"""
<table>
    <thead>
    <tr><th>col1</th><th>col2</th><th>col3</th></tr>
    </thead>
    <tbody>
    <tr><td>v1</td><td>v2</td><td>100</td></tr>
    <tr><td>widest</td><td>v4</td><td>-2000</td></tr>
    <tr><td>v5</td><td>v6</td><td>300</td></tr>
    </tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+--------+------+-------+
| col1   | col2 | col3  |
+--------+------+-------+
| v1     | v2   |   100 |
| widest | v4   | -2000 |
| v5     | v6   |   300 |
+--------+------+-------+
"""

# Three columns, centre-align option
def test_render_table_three_cols_centre_align(mocker):
    content = r"""
<table>
    <thead>
    <tr><th>col1</th><th>col2</th><th>col3</th></tr>
    </thead>
    <tbody>
    <tr><td>v1</td><td>v2</td><td>100</td></tr>
    <tr><td>widest</td><td>v4</td><td>-2000</td></tr>
    <tr><td>v5</td><td>v6</td><td>300</td></tr>
    </tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test, table_align="^")
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+--------+------+-------+
|  col1  | col2 | col3  |
+--------+------+-------+
|   v1   |  v2  |  100  |
| widest |  v4  | -2000 |
|   v5   |  v6  |  300  |
+--------+------+-------+
"""


# Table within a td
def test_render_table_nested(mocker):
    content = r"""
<table>
    <thead>
    <tr><th>col1</th></tr>
    </thead>
    <tbody>
    <tr><td>v1</td></tr>
    <tr><td>widest</td></tr>
    <tr><td> <table><tr><td>insidelonger</td></tr></table> </td></tr>
    </tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+------------------+
| col1             |
+------------------+
| v1               |
| widest           |
| +--------------+ |
| | insidelonger | |
| +--------------+ |
+------------------+
"""

# Table within a td which has a deep row
def test_render_table_nested_deep(mocker):
    content = r"""
<table>
    <thead>
    <tr><th>col1</th></tr>
    </thead>
    <tbody>
    <tr><td>v1</td></tr>
    <tr><td>widest</td></tr>
    <tr><td> <table><tr><td>insidelonger<br>more<br>content</td></tr></table> </td></tr>
    </tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+------------------+
| col1             |
+------------------+
| v1               |
| widest           |
| +--------------+ |
| | insidelonger | |
| | more         | |
| | content      | |
| +--------------+ |
+------------------+
"""

# Table within a td which has a deep row and a footer
def test_render_table_nested_high(mocker):
    content = r"""
<table>
    <thead>
    <tr><th>col1</th></tr>
    </thead>
    <tbody>
    <tr><td>v1</td></tr>
    <tr><td>widest</td></tr>
    <tr><td> <table><tr><td>insidelonger<br>more<br>content</td></tr></table> </td></tr>
    </tbody>
    <tfoot>
    <tr><th>foot1</th></tr>
    </tfoot>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+------------------+
| col1             |
+------------------+
| v1               |
| widest           |
| +--------------+ |
| | insidelonger | |
| | more         | |
| | content      | |
| +--------------+ |
+------------------+
| foot1            |
+------------------+
"""

# Table within a td which mutiple columns one of which is deep
def test_render_table_nested_deep_cols(mocker):
    content = r"""
<table>
    <thead>
    <tr><th>col1</th></tr>
    </thead>
    <tbody>
    <tr><td>v1</td></tr>
    <tr><td>widest</td></tr>
    <tr><td> <table><tr><td>insidelonger<br>more<br> <table><tr><td>three</td><td>deep</td></tr><tr><td>three</td><td>more</td></tr></table> </td></tr></table> </td></tr>
    </tbody>
    <tfoot>
    <tr><th>foot1</th></tr>
    </tfoot>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+----------------------+
| col1                 |
+----------------------+
| v1                   |
| widest               |
| +------------------+ |
| | insidelonger     | |
| | more             | |
| | +-------+------+ | |
| | | three | deep | | |
| | | three | more | | |
| | +-------+------+ | |
| +------------------+ |
+----------------------+
| foot1                |
+----------------------+
"""

# colspan at the bottom (stops col 2 being numeric)
def test_render_table_colspan1(mocker):
    content = r"""
<table>
  <tr>
    <th>Month</th>
    <th>Savings</th>
  </tr>
  <tr>
    <td>January</td>
    <td>$100</td>
  </tr>
  <tr>
    <td>February</td>
    <td>$80</td>
  </tr>
  <tr>
    <td colspan="2">Sum: $180</td>
  </tr>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+----------+---------+
| Month    | Savings |
| January  | $100    |
| February | $80     |
| Sum: $180          |
+--------------------+
"""

# invalid colspan 0 (ignored)
def test_render_table_colspan1_bad(mocker):
    content = r"""
<table>
  <tr>
    <th>Month</th>
    <th>Savings</th>
  </tr>
  <tr>
    <td>January</td>
    <td>$100</td>
  </tr>
  <tr>
    <td>February</td>
    <td>$80</td>
  </tr>
  <tr>
    <td colspan="0">Sum: $180</td>
  </tr>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+-----------+---------+
| Month     | Savings |
| January   | $100    |
| February  | $80     |
| Sum: $180 |
+-----------++
"""

# invalid colspan noise (ignored)
def test_render_table_colspan1_bad2(mocker):
    content = r"""
<table>
  <tr>
    <th>Month</th>
    <th>Savings</th>
  </tr>
  <tr>
    <td>January</td>
    <td>$100</td>
  </tr>
  <tr>
    <td>February</td>
    <td>$80</td>
  </tr>
  <tr>
    <td colspan="noise">Sum: $180</td>
  </tr>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+-----------+---------+
| Month     | Savings |
| January   | $100    |
| February  | $80     |
| Sum: $180 |
+-----------++
"""

# invalid colspan 0.3 (ignored)
def test_render_table_colspan1_bad3(mocker):
    content = r"""
<table>
  <tr>
    <th>Month</th>
    <th>Savings</th>
  </tr>
  <tr>
    <td>January</td>
    <td>$100</td>
  </tr>
  <tr>
    <td>February</td>
    <td>$80</td>
  </tr>
  <tr>
    <td colspan="0.3">Sum: $180</td>
  </tr>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+-----------+---------+
| Month     | Savings |
| January   | $100    |
| February  | $80     |
| Sum: $180 |
+-----------++
"""

# invalid colspan -ve (ignored)
def test_render_table_colspan1_bad4(mocker):
    content = r"""
<table>
  <tr>
    <th>Month</th>
    <th>Savings</th>
  </tr>
  <tr>
    <td>January</td>
    <td>$100</td>
  </tr>
  <tr>
    <td>February</td>
    <td>$80</td>
  </tr>
  <tr>
    <td colspan="-3">Sum: $180</td>
  </tr>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+-----------+---------+
| Month     | Savings |
| January   | $100    |
| February  | $80     |
| Sum: $180 |
+-----------++
"""

# invalid colspan >1000 (ignored)
def TODOREMOVEtest_render_table_colspan1_bad5(mocker):
    content = r"""
<table>
  <tr>
    <th>Month</th>
    <th>Savings</th>
  </tr>
  <tr>
    <td>January</td>
    <td>$100</td>
  </tr>
  <tr>
    <td>February</td>
    <td>$80</td>
  </tr>
  <tr>
    <td colspan="1001">Sum: $180</td>
  </tr>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+-----------+---------+
| Month     | Savings |
+-----------+---------+
| January   |    $100 |
| February  |     $80 |
| Sum: $180 |         |
+-----------+---------+
"""

# colspan in the left middle
def test_render_table_colspan2(mocker):
    content = r"""
<table>
  <tr>
    <th>Month</th>
    <th>Savings</th>
    <th>Third</th>
  </tr>
  <tr>
    <td>January</td>
    <td>$100</td>
    <td>Third</td>
  </tr>
  <tr>
    <td colspan="2">Sum: $180</td>
    <td>Third</td>
  </tr>
  <tr>
    <td>February</td>
    <td>$80</td>
    <td>Third</td>
  </tr>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+----------+---------+-------+
| Month    | Savings | Third |
| January  | $100    | Third |
| Sum: $180          | Third |
| February | $80     | Third |
+----------+---------+-------+
"""

# colspan in the right middle
def test_render_table_colspan3(mocker):
    content = r"""
<table>
  <tr>
    <th>Month</th>
    <th>Savings</th>
    <th>Third</th>
  </tr>
  <tr>
    <td>January</td>
    <td>$100</td>
    <td>Third</td>
  </tr>
  <tr>
    <td>First</td>
    <td colspan="2">Sum: $180</td>
  </tr>
  <tr>
    <td>February</td>
    <td>$80</td>
    <td>Third</td>
  </tr>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+----------+---------+-------+
| Month    | Savings | Third |
| January  | $100    | Third |
| First    | Sum: $180       |
| February | $80     | Third |
+----------+---------+-------+
"""

# colspan at the bottom, with the option turned off (still stops col 2 being numeric)
def test_render_table_colspan4(mocker):
    content = r"""
<table>
  <tr>
    <th>Month</th>
    <th>Savings</th>
  </tr>
  <tr>
    <td>January</td>
    <td>$100</td>
  </tr>
  <tr>
    <td>February</td>
    <td>$80</td>
  </tr>
  <tr>
    <td colspan="2">Sum: $180</td>
  </tr>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+----------+---------+
| Month    | Savings |
| January  | $100    |
| February | $80     |
| Sum: $180          |
+--------------------+
"""

# rowspan in the middle
def test_render_table_rowspan1(mocker):
    content = r"""
<table>
<thead>
  <tr>
    <th>Month</th>
    <th>Savings</th>
    <th>Savings for holiday!</th>
    <th>More</th>
  </tr>
</thead>
<tbody>
  <tr>
    <td>January</td>
    <td>$100</td>
    <td rowspan="3">$100</td>
    <td>$80</td>
  </tr>
  <tr>
    <td>February</td>
    <td>$80</td>
    <td>$80</td>
  </tr>
  <tr>
    <td>March</td>
    <td>$10</td>
    <td>$50</td>
  </tr>
  <tr>
    <td>April</td>
    <td>$70</td>
    <td>$90</td>
    <td>$110</td>
  </tr>
</tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+----------+---------+----------------------+------+
| Month    | Savings | Savings for holiday! | More |
+----------+---------+----------------------+------+
| January  |    $100 |                 $100 |  $80 |
| February |     $80 |                      |  $80 |
| March    |     $10 |                      |  $50 |
| April    |     $70 |                  $90 | $110 |
+----------+---------+----------------------+------+
"""

# rowspan -ve - ignored
def test_render_table_rowspan1_bad(mocker):
    content = r"""
<table>
<thead>
  <tr>
    <th>Month</th>
    <th>Savings</th>
    <th>Savings for holiday!</th>
    <th>More</th>
  </tr>
</thead>
<tbody>
  <tr>
    <td>January</td>
    <td>$100</td>
    <td rowspan="-3">$100</td>
    <td>$80</td>
  </tr>
  <tr>
    <td>February</td>
    <td>$80</td>
    <td>$80</td>
    <td>$120</td>
  </tr>
  <tr>
    <td>March</td>
    <td>$10</td>
    <td>$50</td>
    <td>$130</td>
  </tr>
  <tr>
    <td>April</td>
    <td>$70</td>
    <td>$90</td>
    <td>$110</td>
  </tr>
</tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+----------+---------+----------------------+------+
| Month    | Savings | Savings for holiday! | More |
+----------+---------+----------------------+------+
| January  |    $100 |                 $100 |  $80 |
| February |     $80 |                  $80 | $120 |
| March    |     $10 |                  $50 | $130 |
| April    |     $70 |                  $90 | $110 |
+----------+---------+----------------------+------+
"""


# 2 rowspans in the middle
def test_render_table_rowspan2(mocker):
    content = r"""
<table>
<thead>
  <tr>
    <th>Month</th>
    <th>Savings</th>
    <th>Savings for holiday!</th>
    <th>More</th>
  </tr>
</thead>
<tbody>
  <tr>
    <td>January</td>
    <td>$100</td>
    <td rowspan="3">$100</td>
    <td>$80</td>
  </tr>
  <tr>
    <td>February</td>
    <td>$80</td>
    <td rowspan="2">$80</td>
  </tr>
  <tr>
    <td>March</td>
    <td>$10</td>
  </tr>
  <tr>
    <td>April</td>
    <td>$70</td>
    <td>$90</td>
    <td>$110</td>
  </tr>
</tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+----------+---------+----------------------+------+
| Month    | Savings | Savings for holiday! | More |
+----------+---------+----------------------+------+
| January  |    $100 |                 $100 |  $80 |
| February |     $80 |                      |  $80 |
| March    |     $10 |                      |      |
| April    |     $70 |                  $90 | $110 |
+----------+---------+----------------------+------+
"""

# 2 rowspans in the middle with the option turned off
def test_render_table_col_and_rowspan1(mocker):
    content = r"""
<table>
        <thead>
            <tr>
                <th colspan="2">Name</th>
                <th>Class</th>
                <th>School</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td rowspan="2">Alice</td>
                <td rowspan="2">Brown</td>
                <td>11</td>
                <td rowspan="2">MVM School</td>
            </tr>
            <tr>
                <td>A</td>
            </tr>
            <tr>
                <td rowspan="2">John</td>
                <td rowspan="2">Doe</td>
                <td>3</td>
                <td rowspan="2">LMS School</td>
            </tr>
            <tr>
                <td>B</td>
            </tr>
            <tr>
                <td rowspan="2">Jane</td>
                <td rowspan="2">Smith</td>
                <td>5</td>
                <td rowspan="2">SCPM School</td>
            </tr>
            <tr>
                <td>A</td>
            </tr>
        </tbody>
    </table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+---------------+-------+-------------+
| Name          | Class | School      |
+-------+-------+-------+-------------+
| Alice | Brown | 11    | MVM School  |
|       |       | A     |             |
| John  | Doe   | 3     | LMS School  |
|       |       | B     |             |
| Jane  | Smith | 5     | SCPM School |
|       |       | A     |             |
+-------+-------+-------+-------------+
"""


# from https://en.wikipedia.org/wiki/Moons_of_Mars
# note: images won't be rendered because:
#  a) RENDER_IMAGE_IN_TABLE is set False
#  b) no url is passed to set_renderer so kept offline and so no cache is attempted (no dir)
#  c) an image renderer (plugin) would need to be assumed to be available
#  d) matching the ansi image characters in the result text is too lengthy
def test_render_table_complex2(mocker):
    content = r"""
<table class="wikitable" style="margin:1em auto;">

<tbody><tr style="background:#efefef;">
<th>Label <br /><sup id="cite&#95;ref-32" class="reference"><a href="#cite_note-32"><span class="cite-bracket">&#91;</span>note 1<span class="cite-bracket">&#93;</span></a></sup>
</th>
<th colspan="2">Name and pronunciation
</th>
<th>Image
</th>
<th>Diameter (km)
</th>
<th>Surface<br />area (km<sup>2</sup>)
</th>
<th>Mass (kg)
</th>
<th>Semi-major<br />axis (km)
</th>
<th>Orbital<br />period (h)
</th>
<th>Average moonrise<br />period (h, d)
</th>
<th>Eccentricity
</th>
<th>Inclination (°)<sup id="cite&#95;ref-33" class="reference"><a href="#cite_note-33"><span class="cite-bracket">&#91;</span>note 2<span class="cite-bracket">&#93;</span></a></sup>
</th></tr>
<tr>
<td>I
</td>
<td><a href="/wiki/Phobos_(moon)" title="Phobos (moon)">Phobos</a>
</td>
<td><span class="rt-commentedText nowrap"><span class="IPA nopopups noexcerpt" lang="en-fonipa"><a href="/wiki/Help:IPA/English" title="Help:IPA/English">/<span style="border-bottom:1px dotted"><span title="/ˈ/: primary stress follows">ˈ</span><span title="&#39;f&#39; in &#39;find&#39;">f</span><span title="/oʊ/: &#39;o&#39; in &#39;code&#39;">oʊ</span><span title="&#39;b&#39; in &#39;buy&#39;">b</span><span title="/ə/: &#39;a&#39; in &#39;about&#39;">ə</span><span title="&#39;s&#39; in &#39;sigh&#39;">s</span></span>/</a></span></span><br /><a href="/wiki/Help:Pronunciation_respelling_key" title="Help:Pronunciation respelling key"><i title="English pronunciation respelling"><span style="font-size:90%">FOH</span>-bəs</i></a>
</td>
<td bgcolor="black"><figure class="mw-halign-center" typeof="mw:File"><a href="/wiki/File:Phobos_moon_(large).jpg" class="mw-file-description"><img src="//upload.wikimedia.org/wikipedia/commons/thumb/c/ce/Phobos_moon_%28large%29.jpg/60px-Phobos_moon_%28large%29.jpg" decoding="async" width="50" height="49" class="mw-file-element" srcset="//upload.wikimedia.org/wikipedia/commons/thumb/c/ce/Phobos_moon_%28large%29.jpg/120px-Phobos_moon_%28large%29.jpg 2x" data-file-width="665" data-file-height="650" /></a><figcaption></figcaption></figure>
</td>
<td>22.2&#160;km (13.8&#160;mi)(27×21.6×18.8&#160;km)
</td>
<td>1,548&#160;km<sup>2</sup>
</td>
<td>1.07<span style="margin:0 .15em 0 .25em">×</span>10<sup><span class="nowrap"><span data-sort-value="7001160000000000000♠"></span>16</span></sup>
</td>
<td>9,377&#160;km (5,827&#160;mi)
</td>
<td>7.66
</td>
<td>11.12 h (0.463 d)
</td>
<td>0.0151
</td>
<td>1.093
</td></tr>
<tr>
<td>II
</td>
<td><a href="/wiki/Deimos_(moon)" title="Deimos (moon)">Deimos</a>
</td>
<td><span class="rt-commentedText nowrap"><span class="IPA nopopups noexcerpt" lang="en-fonipa"><a href="/wiki/Help:IPA/English" title="Help:IPA/English">/<span style="border-bottom:1px dotted"><span title="/ˈ/: primary stress follows">ˈ</span><span title="&#39;d&#39; in &#39;dye&#39;">d</span><span title="/aɪ/: &#39;i&#39; in &#39;tide&#39;">aɪ</span><span title="&#39;m&#39; in &#39;my&#39;">m</span><span title="/ə/: &#39;a&#39; in &#39;about&#39;">ə</span><span title="&#39;s&#39; in &#39;sigh&#39;">s</span></span>/</a></span></span><br /><a href="/wiki/Help:Pronunciation_respelling_key" title="Help:Pronunciation respelling key"><i title="English pronunciation respelling"><span style="font-size:90%">DY</span>-məss</i></a>
</td>
<td bgcolor="black"><figure class="mw-halign-center" typeof="mw:File"><a href="/wiki/File:Deimos-viking1.jpg" class="mw-file-description"><img src="//upload.wikimedia.org/wikipedia/commons/thumb/4/43/Deimos-viking1.jpg/60px-Deimos-viking1.jpg" decoding="async" width="50" height="51" class="mw-file-element" srcset="//upload.wikimedia.org/wikipedia/commons/thumb/4/43/Deimos-viking1.jpg/120px-Deimos-viking1.jpg 2x" data-file-width="1015" data-file-height="1033" /></a><figcaption></figcaption></figure>
</td>
<td>12.6&#160;km (7.8&#160;mi)<br />(10×12×16&#160;km)
</td>
<td>483&#160;km<sup>2</sup>
</td>
<td>1.5<span style="margin:0 .15em 0 .25em">×</span>10<sup><span class="nowrap"><span data-sort-value="7001150000000000000♠"></span>15</span></sup>
</td>
<td>23,460&#160;km (14,580&#160;mi)
</td>
<td>30.31
</td>
<td>131 h (5.44 d)
</td>
<td>0.00033
</td>
<td>0.93
</td></tr>
<tr>
<td colspan="12"><figure class="mw-halign-center" typeof="mw:File"><a href="/wiki/File:Mars_Moons_Orbit_distance.jpeg" class="mw-file-description"><img src="//upload.wikimedia.org/wikipedia/commons/thumb/7/79/Mars_Moons_Orbit_distance.jpeg/960px-Mars_Moons_Orbit_distance.jpeg" decoding="async" width="700" height="173" class="mw-file-element" srcset="//upload.wikimedia.org/wikipedia/commons/thumb/7/79/Mars_Moons_Orbit_distance.jpeg/1920px-Mars_Moons_Orbit_distance.jpeg 2x" data-file-width="2750" data-file-height="680" /></a><figcaption></figcaption></figure>The relative sizes of and distance between Mars, Phobos, and Deimos, to scale
<p><i>(Load the image in full size to see both Moons of Mars.)</i>
</p>
</td></tr></tbody>
</table>"""
    # note: we don't pass the url so the image cache will fail which make the test run offline and have a simpler result (the image rendering depends on plugins etc.)
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+-----------------+------------------------------------+---------------+------------------------------------+------------+--------------+-----------------------+------------+-------------------+--------------+---------------------------------+
| Label           | Name and pronunciation             | Image         | Diameter (km)                      | Surface    | Mass (kg)    | Semi-major            | Orbital    | Average moonrise  | Eccentricity | Inclination (°)\x1b[34;2m [ note 2 ]  [2]\x1b[39;22m |
| \x1b[34;2m[ note 1 ]  [1]\x1b[39;22m |                                    |               |                                    | area (km2) |              | axis (km)             | period (h) | period (h, d)     |              |                                 |
| I               | \x1b[34;2mPhobos [3]\x1b[39;22m  | \x1b[34;2m/ ˈ f oʊ b ə s / [4]\x1b[39;22m | \x1b[33;2m[IMG] [6]\x1b[39;22m     | 22.2\xa0km (13.8\xa0mi)(27×21.6×18.8\xa0km) | 1,548\xa0km2  | 1.07 × 10 16 | 9,377\xa0km (5,827\xa0mi)   | 7.66       | 11.12 h (0.463 d) | 0.0151       | 1.093                           |
|                 |             | \x1b[34;2;3mFOH -bəs\x1b[23m [5]\x1b[39;22m         | \x1b[34;2m[IMG LINK 7]\x1b[39;22m  |                                    |            |              |                       |            |                   |              |                                 |
| II              | \x1b[34;2mDeimos [8]\x1b[39;22m  | \x1b[34;2m/ ˈ d aɪ m ə s / [9]\x1b[39;22m | \x1b[33;2m[IMG] [11]\x1b[39;22m    | 12.6\xa0km (7.8\xa0mi)                   | 483\xa0km2    | 1.5 × 10 15  | 23,460\xa0km (14,580\xa0mi) | 30.31      | 131 h (5.44 d)    | 0.00033      | 0.93                            |
|                 |             | \x1b[34;2;3mDY -məss\x1b[23m [10]\x1b[39;22m        | \x1b[34;2m[IMG LINK 12]\x1b[39;22m | (10×12×16\xa0km)                      |            |              |                       |            |                   |              |                                 |
| \x1b[33;2m[IMG] [13]\x1b[39;22m                                                                                                                                                                                                                                      |
| \x1b[34;2m[IMG LINK 14]\x1b[39;22mThe relative sizes of and distance between Mars, Phobos,                                                                                                                                                                           |
| and Deimos, to scale                                                                                                                                                                                                                            |
|                                                                                                                                                                                                                                                 |
| \x1b[3m(Load the image in full size to see both Moons of Mars.)\x1b[23m                                                                                                                                                                                        |
|                                                                                                                                                                                                                                                 |
+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
"""

def test_render_table_complex3(mocker):
    content = r"""
<table class="nowraplinks hlist mw-collapsible autocollapse navbox-inner mw-made-collapsible mw-collapsed" style="border-spacing:0;background:transparent;color:inherit"><tbody><tr><th scope="col" class="navbox-title" colspan="2"><button type="button" class="mw-collapsible-toggle mw-collapsible-toggle-default mw-collapsible-toggle-collapsed" aria-expanded="false" tabindex="0"><span class="mw-collapsible-text">show</span></button><div id="Authority_control_databases_frameless&amp;#124;text-top&amp;#124;10px&amp;#124;alt=Edit_this_at_Wikidata&amp;#124;link=https&amp;#58;//www.wikidata.org/wiki/Q177268#identifiers&amp;#124;class=noprint&amp;#124;Edit_this_at_Wikidata644" style="font-size:114%;margin:0 4em"><a href="/wiki/Help:Authority_control" title="Help:Authority control">Authority control databases</a> <span class="mw-valign-text-top noprint" typeof="mw:File/Frameless"><a href="https://www.wikidata.org/wiki/Q177268#identifiers" title="Edit this at Wikidata"><img alt="Edit this at Wikidata" src="//upload.wikimedia.org/wikipedia/en/thumb/8/8a/OOjs_UI_icon_edit-ltr-progressive.svg/20px-OOjs_UI_icon_edit-ltr-progressive.svg.png" decoding="async" width="10" height="10" class="mw-file-element" data-file-width="20" data-file-height="20"></a></span></div></th></tr><tr hidden="until-found"><th scope="row" class="navbox-group" style="width:1%">National</th><td class="navbox-list-with-group navbox-list navbox-odd" style="width:100%;padding:0"><div style="padding:0 0.25em"><ul><li><span class="uid"><a rel="nofollow" class="external text" href="https://id.loc.gov/authorities/sh85117638">United States</a></span></li><li><span class="uid"><a rel="nofollow" class="external text" href="https://www.nli.org.il/en/authorities/987007558487105171">Israel</a></span></li></ul></div></td></tr><tr hidden="until-found"><th scope="row" class="navbox-group" style="width:1%">Other</th><td class="navbox-list-with-group navbox-list navbox-even" style="width:100%;padding:0"><div style="padding:0 0.25em"><ul><li><span class="uid"><a rel="nofollow" class="external text" href="https://lux.collections.yale.edu/view/concept/50a5af2c-3ff0-414e-a348-f92d50351c8d">Yale LUX</a></span></li></ul></div></td></tr></tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+-----------------------------------------+
| show                                    |
|                                         |
| \x1b[34;2mAuthority control databases [1]\x1b[39;22m         |
| \x1b[33;2m[IMG] Edit this at Wikidata [2]\x1b[39;22m         |
| \x1b[34;2m[IMG LINK 3]\x1b[39;22m                            |
|                                         |
|                  |  • \x1b[34;2mUnited States [4]\x1b[39;22m |
| National         |  • \x1b[34;2mIsrael [5]\x1b[39;22m        |
|                  |                      |
| Other            | Yale LUX             |
|                  |                      |
+------------------+----------------------+
"""


# from https://mdn.github.io/learning-area/html/tables/assessment-finished/planets-data.html
def test_render_table_complex4(mocker):
    content = r"""
    <table>
      <caption>Data about the planets of our solar system (Planetary facts taken from <a href="https://nssdc.gsfc.nasa.gov/planetary/factsheet/">Nasa's Planetary Fact Sheet - Metric</a>).</caption>
      <colgroup>
        <col span="2">
        <col style="border: 2px solid black">
        <col span="9">
      </colgroup>
      <thead>
        <tr>
          <td colspan="2"></td>
          <th scope="col">Name</th>
          <th scope="col">Mass (10<sup>24</sup>kg)</th>
          <th scope="col">Diameter (km)</th>
          <th scope="col">Density (kg/m<sup>3</sup>)</th>
          <th scope="col">Gravity (m/s<sup>2</sup>)</th>
          <th scope="col">Length of day (hours)</th>
          <th scope="col">Distance from Sun (10<sup>6</sup>km)</th>
          <th scope="col">Mean temperature (°C)</th>
          <th scope="col">Number of moons</th>
          <th scope="col">Notes</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <th rowspan="4" colspan="2" scope="rowgroup">Terrestrial planets</th>
          <th scope="row">Mercury</th>
          <td>0.330</td>
          <td>4,879</td>
          <td>5427</td>
          <td>3.7</td>
          <td>4222.6</td>
          <td>57.9</td>
          <td>167</td>
          <td>0</td>
          <td>Closest to the Sun</td>
        </tr>
        <tr>
          <th scope="row">Venus</th>
          <td>4.87</td>
          <td>12,104</td>
          <td>5243</td>
          <td>8.9</td>
          <td>2802.0</td>
          <td>108.2</td>
          <td>464</td>
          <td>0</td>
          <td></td>
        </tr>
        <tr>
          <th scope="row">Earth</th>
          <td>5.97</td>
          <td>12,756</td>
          <td>5514</td>
          <td>9.8</td>
          <td>24.0</td>
          <td>149.6</td>
          <td>15</td>
          <td>1</td>
          <td>Our world</td>
        </tr>
        <tr>
          <th scope="row">Mars</th>
          <td>0.642</td>
          <td>6,792</td>
          <td>3933</td>
          <td>3.7</td>
          <td>24.7</td>
          <td>227.9</td>
          <td>-65</td>
          <td>2</td>
          <td>The red planet</td>
        </tr>
        <tr>
          <th rowspan="4" scope="rowgroup">Jovian planets</th>
          <th rowspan="2" scope="rowgroup">Gas giants</th>
          <th scope="row">Jupiter</th>
          <td>1898</td>
          <td>142,984</td>
          <td>1326</td>
          <td>23.1</td>
          <td>9.9</td>
          <td>778.6</td>
          <td>-110</td>
          <td>67</td>
          <td>The largest planet</td>
        </tr>
        <tr>
          <th scope="row">Saturn</th>
          <td>568</td>
          <td>120,536</td>
          <td>687</td>
          <td>9.0</td>
          <td>10.7</td>
          <td>1433.5</td>
          <td>-140</td>
          <td>62</td>
          <td></td>
        </tr>
        <tr>
          <th rowspan="2" scope="rowgroup">Ice giants</th>
          <th scope="row">Uranus</th>
          <td>86.8</td>
          <td>51,118</td>
          <td>1271</td>
          <td>8.7</td>
          <td>17.2</td>
          <td>2872.5</td>
          <td>-195</td>
          <td>27</td>
          <td></td>
        </tr>
        <tr>
          <th scope="row">Neptune</th>
          <td>102</td>
          <td>49,528</td>
          <td>1638</td>
          <td>11.0</td>
          <td>16.1</td>
          <td>4495.1</td>
          <td>-200</td>
          <td>14</td>
          <td></td>
        </tr>
        <tr>
          <th colspan="2" scope="row">Dwarf planets</th>
          <th scope="row">Pluto</th>
          <td>0.0146</td>
          <td>2,370</td>
          <td>2095</td>
          <td>0.7</td>
          <td>153.3</td>
          <td>5906.4</td>
          <td>-225</td>
          <td>5</td>
          <td>Declassified as a planet in 2006, but this <a href="https://www.usatoday.com/story/tech/2014/10/02/pluto-planet-solar-system/16578959/">remains controversial</a>.</td>
        </tr>
      </tbody>
    </table>
"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+-----------------------------+---------+---------------+---------------+-----------------+----------------+-----------------------+---------------------------+-----------------------+-----------------+-----------------------------------------------------------------------+
|                             | Name    | Mass (1024kg) | Diameter (km) | Density (kg/m3) | Gravity (m/s2) | Length of day (hours) | Distance from Sun (106km) | Mean temperature (°C) | Number of moons | Notes                                                                 |
+-----------------------------+---------+---------------+---------------+-----------------+----------------+-----------------------+---------------------------+-----------------------+-----------------+-----------------------------------------------------------------------+
| Terrestrial planets         | Mercury |         0.330 |         4,879 |            5427 |            3.7 |                4222.6 |                      57.9 |                   167 |               0 | Closest to the Sun                                                    |
|                             | Venus   |          4.87 |        12,104 |            5243 |            8.9 |                2802.0 |                     108.2 |                   464 |               0 |                                                                       |
|                             | Earth   |          5.97 |        12,756 |            5514 |            9.8 |                  24.0 |                     149.6 |                    15 |               1 | Our world                                                             |
|                             | Mars    |         0.642 |         6,792 |            3933 |            3.7 |                  24.7 |                     227.9 |                   -65 |               2 | The red planet                                                        |
| Jovian planets | Gas giants | Jupiter |          1898 |       142,984 |            1326 |           23.1 |                   9.9 |                     778.6 |                  -110 |              67 | The largest planet                                                    |
|                |            | Saturn  |           568 |       120,536 |             687 |            9.0 |                  10.7 |                    1433.5 |                  -140 |              62 |                                                                       |
|                | Ice giants | Uranus  |          86.8 |        51,118 |            1271 |            8.7 |                  17.2 |                    2872.5 |                  -195 |              27 |                                                                       |
|                |            | Neptune |           102 |        49,528 |            1638 |           11.0 |                  16.1 |                    4495.1 |                  -200 |              14 |                                                                       |
| Dwarf planets               | Pluto   |        0.0146 |         2,370 |            2095 |            0.7 |                 153.3 |                    5906.4 |                  -225 |               5 | Declassified as a planet in 2006, but this \x1b[34;2mremains controversial [1]\x1b[39;22m. |
+-----------------------------+---------+---------------+---------------+-----------------+----------------+-----------------------+---------------------------+-----------------------+-----------------+-----------------------------------------------------------------------+
"""

# from https://mdn.github.io/learning-area/html/tables/assessment-finished/planets-data.html
def test_render_table_complex4_with_separators(mocker):
    content = r"""
    <table>
      <caption>Data about the planets of our solar system (Planetary facts taken from <a href="https://nssdc.gsfc.nasa.gov/planetary/factsheet/">Nasa's Planetary Fact Sheet - Metric</a>).</caption>
      <colgroup>
        <col span="2">
        <col style="border: 2px solid black">
        <col span="9">
      </colgroup>
      <thead>
        <tr>
          <td colspan="2"></td>
          <th scope="col">Name</th>
          <th scope="col">Mass (10<sup>24</sup>kg)</th>
          <th scope="col">Diameter (km)</th>
          <th scope="col">Density (kg/m<sup>3</sup>)</th>
          <th scope="col">Gravity (m/s<sup>2</sup>)</th>
          <th scope="col">Length of day (hours)</th>
          <th scope="col">Distance from Sun (10<sup>6</sup>km)</th>
          <th scope="col">Mean temperature (°C)</th>
          <th scope="col">Number of moons</th>
          <th scope="col">Notes</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <th rowspan="4" colspan="2" scope="rowgroup">Terrestrial planets</th>
          <th scope="row">Mercury</th>
          <td>0.330</td>
          <td>4,879</td>
          <td>5427</td>
          <td>3.7</td>
          <td>4222.6</td>
          <td>57.9</td>
          <td>167</td>
          <td>0</td>
          <td>Closest to the Sun</td>
        </tr>
        <tr>
          <th scope="row">Venus</th>
          <td>4.87</td>
          <td>12,104</td>
          <td>5243</td>
          <td>8.9</td>
          <td>2802.0</td>
          <td>108.2</td>
          <td>464</td>
          <td>0</td>
          <td></td>
        </tr>
        <tr>
          <th scope="row">Earth</th>
          <td>5.97</td>
          <td>12,756</td>
          <td>5514</td>
          <td>9.8</td>
          <td>24.0</td>
          <td>149.6</td>
          <td>15</td>
          <td>1</td>
          <td>Our world</td>
        </tr>
        <tr>
          <th scope="row">Mars</th>
          <td>0.642</td>
          <td>6,792</td>
          <td>3933</td>
          <td>3.7</td>
          <td>24.7</td>
          <td>227.9</td>
          <td>-65</td>
          <td>2</td>
          <td>The red planet</td>
        </tr>
        <tr>
          <th rowspan="4" scope="rowgroup">Jovian planets</th>
          <th rowspan="2" scope="rowgroup">Gas giants</th>
          <th scope="row">Jupiter</th>
          <td>1898</td>
          <td>142,984</td>
          <td>1326</td>
          <td>23.1</td>
          <td>9.9</td>
          <td>778.6</td>
          <td>-110</td>
          <td>67</td>
          <td>The largest planet</td>
        </tr>
        <tr>
          <th scope="row">Saturn</th>
          <td>568</td>
          <td>120,536</td>
          <td>687</td>
          <td>9.0</td>
          <td>10.7</td>
          <td>1433.5</td>
          <td>-140</td>
          <td>62</td>
          <td></td>
        </tr>
        <tr>
          <th rowspan="2" scope="rowgroup">Ice giants</th>
          <th scope="row">Uranus</th>
          <td>86.8</td>
          <td>51,118</td>
          <td>1271</td>
          <td>8.7</td>
          <td>17.2</td>
          <td>2872.5</td>
          <td>-195</td>
          <td>27</td>
          <td></td>
        </tr>
        <tr>
          <th scope="row">Neptune</th>
          <td>102</td>
          <td>49,528</td>
          <td>1638</td>
          <td>11.0</td>
          <td>16.1</td>
          <td>4495.1</td>
          <td>-200</td>
          <td>14</td>
          <td></td>
        </tr>
        <tr>
          <th colspan="2" scope="row">Dwarf planets</th>
          <th scope="row">Pluto</th>
          <td>0.0146</td>
          <td>2,370</td>
          <td>2095</td>
          <td>0.7</td>
          <td>153.3</td>
          <td>5906.4</td>
          <td>-225</td>
          <td>5</td>
          <td>Declassified as a planet in 2006, but this <a href="https://www.usatoday.com/story/tech/2014/10/02/pluto-planet-solar-system/16578959/">remains controversial</a>.</td>
        </tr>
      </tbody>
    </table>
"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test, table_separators="true")
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+-----------------------------+---------+---------------+---------------+-----------------+----------------+-----------------------+---------------------------+-----------------------+-----------------+-----------------------------------------------------------------------+
|                             | Name    | Mass (1024kg) | Diameter (km) | Density (kg/m3) | Gravity (m/s2) | Length of day (hours) | Distance from Sun (106km) | Mean temperature (°C) | Number of moons | Notes                                                                 |
+-----------------------------+---------+---------------+---------------+-----------------+----------------+-----------------------+---------------------------+-----------------------+-----------------+-----------------------------------------------------------------------+
| Terrestrial planets         | Mercury |         0.330 |         4,879 |            5427 |            3.7 |                4222.6 |                      57.9 |                   167 |               0 | Closest to the Sun                                                    |
|                             +---------+---------------+---------------+-----------------+----------------+-----------------------+---------------------------+-----------------------+-----------------+-----------------------------------------------------------------------+
|                             | Venus   |          4.87 |        12,104 |            5243 |            8.9 |                2802.0 |                     108.2 |                   464 |               0 |                                                                       |
|                             +---------+---------------+---------------+-----------------+----------------+-----------------------+---------------------------+-----------------------+-----------------+-----------------------------------------------------------------------+
|                             | Earth   |          5.97 |        12,756 |            5514 |            9.8 |                  24.0 |                     149.6 |                    15 |               1 | Our world                                                             |
|                             +---------+---------------+---------------+-----------------+----------------+-----------------------+---------------------------+-----------------------+-----------------+-----------------------------------------------------------------------+
|                             | Mars    |         0.642 |         6,792 |            3933 |            3.7 |                  24.7 |                     227.9 |                   -65 |               2 | The red planet                                                        |
|                             +---------+---------------+---------------+-----------------+----------------+-----------------------+---------------------------+-----------------------+-----------------+-----------------------------------------------------------------------+
| Jovian planets | Gas giants | Jupiter |          1898 |       142,984 |            1326 |           23.1 |                   9.9 |                     778.6 |                  -110 |              67 | The largest planet                                                    |
|                |            +---------+---------------+---------------+-----------------+----------------+-----------------------+---------------------------+-----------------------+-----------------+-----------------------------------------------------------------------+
|                |            | Saturn  |           568 |       120,536 |             687 |            9.0 |                  10.7 |                    1433.5 |                  -140 |              62 |                                                                       |
|                |            +---------+---------------+---------------+-----------------+----------------+-----------------------+---------------------------+-----------------------+-----------------+-----------------------------------------------------------------------+
|                | Ice giants | Uranus  |          86.8 |        51,118 |            1271 |            8.7 |                  17.2 |                    2872.5 |                  -195 |              27 |                                                                       |
|                |            +---------+---------------+---------------+-----------------+----------------+-----------------------+---------------------------+-----------------------+-----------------+-----------------------------------------------------------------------+
|                |            | Neptune |           102 |        49,528 |            1638 |           11.0 |                  16.1 |                    4495.1 |                  -200 |              14 |                                                                       |
|                |            +---------+---------------+---------------+-----------------+----------------+-----------------------+---------------------------+-----------------------+-----------------+-----------------------------------------------------------------------+
| Dwarf planets               | Pluto   |        0.0146 |         2,370 |            2095 |            0.7 |                 153.3 |                    5906.4 |                  -225 |               5 | Declassified as a planet in 2006, but this \x1b[34;2mremains controversial [1]\x1b[39;22m. |
+-----------------------------+---------+---------------+---------------+-----------------+----------------+-----------------------+---------------------------+-----------------------+-----------------+-----------------------------------------------------------------------+
"""


# Calendar table from https://en.wikipedia.org/wiki/Portal:Current_events
def test_render_table_complex9(mocker):
    content = r"""
<table class="current-events-calendar"><caption><span class="noprint"><a href="/wiki/Portal:Current_events/March_2026" title="Portal:Current events/March 2026">◀</a></span><span><a href="/wiki/Portal:Current_events/April_2026" title="Portal:Current events/April 2026">April 2026</a></span><span class="noprint"><a href="/wiki/Portal:Current_events/May_2026" title="Portal:Current events/May 2026">▶</a></span></caption><tbody>
<tr><th>S</th><th>M</th><th>T</th><th>W</th><th>T</th><th>F</th><th>S</th></tr>
<tr><td></td><td></td><td></td><td>1</td><td>2</td><td>3</td><td>4</td></tr>
<tr><td>5</td><td>6</td><td>7</td><td>8</td><td>9</td><td>10</td><td>11</td></tr>
<tr><td>12</td><td>13</td><td>14</td><td>15</td><td>16</td><td>17</td><td>18</td></tr>
<tr><td>19</td><td>20</td><td>21</td><td><a href="#2026_April_22">22</a></td><td><a href="#2026_April_23">23</a></td><td><a href="#2026_April_24">24</a></td><td><a href="#2026_April_25">25</a></td></tr>
<tr><td><a href="#2026_April_26">26</a></td><td><a href="#2026_April_27">27</a></td><td><a href="#2026_April_28">28</a></td><td>29</td><td>30</td><td></td><td></td></tr>
<tr class="current-events-calendar-footer noprint"><td colspan="7"><a href="/wiki/Portal:Current_events/April_2026" title="Portal:Current events/April 2026">More April 2026 events...&nbsp;&nbsp;&nbsp;</a></td></tr></tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+--------+--------+--------+--------+--------+--------+--------+
| S      | M      | T      | W      | T      | F      | S      |
|        |        |        | 1      | 2      | 3      | 4      |
| 5      | 6      | 7      | 8      | 9      | 10     | 11     |
| 12     | 13     | 14     | 15     | 16     | 17     | 18     |
| 19     | 20     | 21     | \x1b[34;2m22 [1]\x1b[39;22m | \x1b[34;2m23 [2]\x1b[39;22m | \x1b[34;2m24 [3]\x1b[39;22m | \x1b[34;2m25 [4]\x1b[39;22m |
| \x1b[34;2m26 [5]\x1b[39;22m | \x1b[34;2m27 [6]\x1b[39;22m | \x1b[34;2m28 [7]\x1b[39;22m | 29     | 30     |        |        |
| \x1b[34;2mMore April 2026 events...  [8]\x1b[39;22m                               |
+--------------------------------------------------------------+
"""


# 4.9.13 Examples table (bottom part of table 45 of the Smithsonian physical tables, Volume 71) from https://html.spec.whatwg.org/multipage/tables.html#tabular-data-processing-model
def test_render_table_complex10(mocker):
    content = r"""
<table>
 <caption>Specification values: <b>Steel</b>, <b>Castings</b>,
 Ann. A.S.T.M. A27-16, Class B;* P max. 0.06; S max. 0.05.</caption>
 <thead>
  <tr>
   <th rowspan=2>Grade.</th>
   <th rowspan=2>Yield Point.</th>
   <th colspan=2>Ultimate tensile strength</th>
   <th rowspan=2>Per cent elong. 50.8&nbsp;mm or 2&nbsp;in.</th>
   <th rowspan=2>Per cent reduct. area.</th>
  </tr>
  <tr>
   <th>kg/mm<sup>2</sup></th>
   <th>lb/in<sup>2</sup></th>
  </tr>
 </thead>
 <tbody>
  <tr>
   <td>Hard</td>
   <td>0.45 ultimate</td>
   <td>56.2</td>
   <td>80,000</td>
   <td>15</td>
   <td>20</td>
  </tr>
  <tr>
   <td>Medium</td>
   <td>0.45 ultimate</td>
   <td>49.2</td>
   <td>70,000</td>
   <td>18</td>
   <td>25</td>
  </tr>
  <tr>
   <td>Soft</td>
   <td>0.45 ultimate</td>
   <td>42.2</td>
   <td>60,000</td>
   <td>22</td>
   <td>30</td>
  </tr>
 </tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+--------+---------------+------------------------------+----------------------------------+------------------------+
| Grade. | Yield Point.  | Ultimate tensile strength    | Per cent elong. 50.8\xa0mm or 2\xa0in. | Per cent reduct. area. |
|        |               | kg/mm2        | lb/in2       |                                  |                        |
+--------+---------------+---------------+--------------+----------------------------------+------------------------+
| Hard   | 0.45 ultimate |          56.2 |       80,000 |                               15 |                     20 |
| Medium | 0.45 ultimate |          49.2 |       70,000 |                               18 |                     25 |
| Soft   | 0.45 ultimate |          42.2 |       60,000 |                               22 |                     30 |
+--------+---------------+---------------+--------------+----------------------------------+------------------------+
"""

# Invalid, empty row: no longer caught
def test_render_table_invalid_empty_row(mocker):
    content = r"""
<table>
    <thead>
    <tr><th>col1</th></tr>
    </thead>
    <tbody>
    <tr><td>v1</td></tr>
    <tr><td>widest</td></tr>
    <tr></tr>
    </tbody>
</table>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    # with catch: assert r == "Error rendering tableInvalid table: empty slot row"
    # without catch: we'd rather see an empty row than no table at all
    assert r == """+--------+
| col1   |
+--------+
| v1     |
| widest |
++
"""

# Simple links were getting removed by readability (after apt-get install python3-readability)
def test_render_table_readability_loss(mocker):
    content = """<!DOCTYPE html>
<html lang="en">
<body>

<div class="container">

<table class="table table-striped">
	<tr>
		<th class="text-center">Date<span class="tzfix_zone"> (UTC)</span></th>
		<th class="text-center">Event</th>
	</tr>

	<tr>
		<td class="minimal-column"><time class="tzfix_time" datetime="2026-03-16T08:07+0000">2026-03-16 08:07</time></td>
		<td> <a href="/repository/nix_unstable">nixpkgs unstable</a> has caught up with the newest version</td>
	</tr>

	<tr>
		<td class="minimal-column"><time class="tzfix_time" datetime="2026-03-12T02:16+0000">2026-03-12 02:16</time></td>
		<td> <a href="/repository/kali_rolling">Kali Linux Rolling</a> has caught up with the newest version</td>
	</tr>

	<tr>
		<td class="minimal-column"><time class="tzfix_time" datetime="2026-03-07T11:17+0000">2026-03-07 11:17</time></td>
		<td> <a href="/repository/raspbian_testing">Raspbian Testing</a> has caught up with the newest version</td>
	</tr>

	<tr>
		<td class="minimal-column"><time class="tzfix_time" datetime="2026-03-07T09:00+0000">2026-03-07 09:00</time></td>
		<td> <a href="/repository/debian_14">Debian 14</a> has caught up with the newest version</td>
	</tr>

	<tr>
		<td class="minimal-column"><time class="tzfix_time" datetime="2026-03-05T03:08+0000">2026-03-05 03:08</time></td>
		<td> <a href="/repository/debian_unstable">Debian Unstable</a>, <a href="/repository/devuan_unstable">Devuan Unstable</a> have caught up with the newest version</td>
	</tr>

	<tr>
		<td class="minimal-column"><time class="tzfix_time" datetime="2026-03-04T02:24+0000">2026-03-04 02:24</time></td>
		<td>Project
				added to <a href="/repository/gnuguix">GNU Guix</a></td>
	</tr>

	<tr>
		<td class="minimal-column"><time class="tzfix_time" datetime="2026-03-02T13:11+0000">2026-03-02 13:11</time></td>
		<td> <a href="/repository/aur">AUR</a> has caught up with the newest version</td>
	</tr>
</table>

</div>

</body>
</html>"""
    toreturn = ansicat.set_renderer(content, "", "text/html", theme=offthemes._test)
    toreturn.center=False
    toreturn.set_mode("full")   # note: avoids any readability at top-level
    r = toreturn.get_body()
    assert r == """+------------------+-------------------------------------------------------------------------+
| Date  (UTC)      | Event                                                                   |
| 2026-03-16 08:07 | \x1b[34;2mnixpkgs unstable [1]\x1b[39;22m has caught up with the newest version              |
| 2026-03-12 02:16 | \x1b[34;2mKali Linux Rolling [2]\x1b[39;22m has caught up with the newest version            |
| 2026-03-07 11:17 | \x1b[34;2mRaspbian Testing [3]\x1b[39;22m has caught up with the newest version              |
| 2026-03-07 09:00 | \x1b[34;2mDebian 14 [4]\x1b[39;22m has caught up with the newest version                     |
| 2026-03-05 03:08 | \x1b[34;2mDebian Unstable [5]\x1b[39;22m, \x1b[34;2mDevuan Unstable [6]\x1b[39;22m have caught up with the newest |
|                  | version                                                                 |
| 2026-03-04 02:24 | Project added to \x1b[34;2mGNU Guix [7]\x1b[39;22m                                           |
| 2026-03-02 13:11 | \x1b[34;2mAUR [8]\x1b[39;22m has caught up with the newest version                           |
+------------------+-------------------------------------------------------------------------+
"""
