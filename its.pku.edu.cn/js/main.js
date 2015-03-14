function setInfo(data)
{
    $("#loading_dialog").modal('hide');
    if(data.check_status === true){
        $('#status_tr').attr("class","success");
        $('#connect_btn').attr("class","btn btn-success btn-lg center-block");
        $('#status').text("连接成功")
    }else if(data.check_status === false){
        $('#status_tr').attr("class","danger");
        $('#connect_btn').attr("class","btn btn-danger btn-lg center-block");
        $('#status').text("连接失败")
    }else{
        $('#status_tr').attr("class","danger");
        $('#connect_btn').attr("class","btn btn-danger btn-lg center-block");
        $('#status').text("服务器无响应")
    }
    $('#check_time').text(data.check_time);
    $('#connect_time').text(data.request_time);
    $('#plan_time').text(data.next_reconnect_time);
    $('#status_detail').html(data.request_response);
}

function getinfo() {
    $("#loading_dialog").modal('show');
    $.ajax({
        url: "http://atom.catofes.com:8000/connect",
        method: 'GET',
        timeout: 1000
    }).done(function (data) {
        setInfo(data)
    }).fail(function (data) {
        setInfo(data)
    });
}

function connect() {
    $("#loading_dialog").modal('show');
    $.ajax({
        url: "http://atom.catofes.com:8000/connect",
        method: 'PUT',
        timeout: 1000
    }).done(function(data){
        setInfo(data)
    }).fail(function(data){
        setInfo(data)
    })
}
$('#status_tr').click(
    function(){
        if(document.status_open == true){
            document.status_open = false
            $('#status_dialog').modal('hide')
        }else{
            document.status_open = true
            $('#status_dialog').modal('show')
        }
    }
)
$(document).ready(getinfo())