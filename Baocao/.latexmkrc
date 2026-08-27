# XeLaTeX: file dùng fontspec + polyglossia (tiếng Việt, Times/TeX Gyre).
# $pdf_mode = 5 nghĩa là xelatex -> xdvipdfmx -> pdf.
$pdf_mode = 5;
$xelatex = 'xelatex -synctex=1 -interaction=nonstopmode -file-line-error %O %S';
$pdflatex = 'xelatex -synctex=1 -interaction=nonstopmode -file-line-error %O %S';
