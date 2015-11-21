function setInfo(data) {
    document.ajaxdata = data;
    $("#loading_dialog").modal('hide');
    if (data.check_status === true) {
        $('#status_tr').attr("class", "success");
        $('#connect_btn').attr("class", "btn btn-success btn-lg center-block");
        $('#status').text("连接成功")
    } else if (data.check_status === false) {
        $('#status_tr').attr("class", "danger");
        $('#connect_btn').attr("class", "btn btn-danger btn-lg center-block");
        $('#status').text("连接失败")
    } else {
        $('#status_tr').attr("class", "danger");
        $('#connect_btn').attr("class", "btn btn-danger btn-lg center-block disabled");
        $('#status').text("服务器无响应")
    }
    $('#check_time').text(data.check_time);
    $('#connect_time').text(data.request_time);
    $('#plan_time').text(data.next_reconnect_time);
    $('#status_detail').html(data.request_response);
    $('select#output_selector').empty();
    for (var i in data.allow_destination) {
        $('<option value="' + data.allow_destination[i].id + '">'
            + data.allow_destination[i].name + '</option>').appendTo('select#output_selector')
    }
    if (data.IP != null) {
        $('tr.ip').removeClass("hidden");
        $('tr.output').removeClass("hidden");
        $('#client_ip').html(data.IP);
        if (data.destination == "") {
            data.destination = "main";
        }
        $('#client_output').html(data.destination);
        $('button#change_btn').attr("class", "btn btn-success btn-lg center-block");
    } else {
        $('tr.ip').addClass("hidden");
        $('tr.output').addClass("hidden");
        $('button#change_btn').attr("class", "btn btn-danger btn-lg center-block disabled");
    }
}

function getinfo() {
    $("#loading_dialog").modal('show');
    $.ajax({
        url: "/connect",
        method: 'GET',
        timeout: 10000
    }).done(function (data) {
        setInfo(data)
    }).fail(function (data) {
        setInfo(data)
    });
}

function connect() {
    $("#loading_dialog").modal('show');
    document.ajaxcount++;
    if (document.ajaxcount < 5 && document.ajaxdata.check_status === true) {
        getinfo();
        return;
    }
    $.ajax({
        url: "/connect",
        method: 'POST',
        timeout: 10000
    }).done(function (data) {
        setInfo(data)
    }).fail(function (data) {
        setInfo(data)
    });
}

function change() {
    dest = $("select#output_selector")[0].value;
    $("#loading_dialog").modal('show');
    $.ajax({
        url: "/connect?dest=" + dest,
        method: 'PUT',
        timeout: 10000
    }).done(function () {
        $("#loading_dialog").modal('hide');
        getinfo()
    }).fail(function () {
        $("#loading_dialog").modal('hide');
        $('#status_tr').attr("class", "danger");
        $('button#change_btn').attr("class", "btn btn-danger btn-lg center-block");
        $('#status').text("失败")
    })
}

$('#status_tr').click(
    function () {
        if (document.status_open == true) {
            document.status_open = false;
            $('#status_dialog').modal('hide')
        } else {
            document.status_open = true;
            $('#status_dialog').modal('show')
        }
    }
);
document.ajaxcount = 0;
$(document).ready(getinfo());
