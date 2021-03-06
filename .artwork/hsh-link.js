// vim: tabstop=4 expandtab

var modified = 0;

function body_loaded() {
	document.getElementById("store").style.visibility="hidden"; 
}

function data_modified() {
	document.getElementById("store").style.visibility="inherit";
	modified = 1;
}

function output_selected() {
	if (modified == 0) {
		window.location.href="?output=" + document.getElementById("output").value;
	}
}

function update_lineno() {
    var area = document.getElementById("content")
    document.getElementById("lineno").value = area.value.substr(0, area.selectionStart).split("\n").length;
}
