            
var ticket = null;
let flag_redaman = false;
let flag_speed = false;
let flag_save = false;
let autoSave;
let timeoutSave;
var whitelist = null;
let iMax = null;
let iTimer = 0;
let serviceNumber;

var flagPcrf = false;
var flagToken = false;
var flagMyIp = false;
var flagNd = false;
var flagRadius = false;
var ticket = null;
let uuid;


//inisiasi prefix backend
let urlbackend = '/check/'

$(document).ready(function() {
    var alert_del = document.getElementById('ticket-alert');
    alert_del.addEventListener('click', function () {
        $('.alert-del').addClass('hidden')
    })
    $.ajaxSetup({
        headers: {
            'X-CSRF-TOKEN': $('meta[name="csrf-token"]').attr('content')
        }
    });

    /*
    saat pertama kali web dibuka function Validate langsung di jalankan untuk mengetahui pengguna menggunakan jaringan IndiHome atau bukan
    */
    ValidateAccess();

    window.scrollTo({
        top: 0,
        behavior: 'smooth'
    });
    

    $('#btn-closing-success').click(function(e) {
        $('#result-check').remove()
        $('#trx-footer').remove()
        $('#section_tracking_result_information').remove()
        $('#section_success').removeClass('hidden');
    });

    $('#btn-closing-failed').click(function(e) {
        e.preventDefault();
        window.location.href = window.location.href;
    });

    $('#btn-message-failed').click(function(e) {
        e.preventDefault();
        window.location.href = window.location.href;
    });

    // tombol retry ketika hasil belun kayak atau ketika gagal pada setiap step
    $('#retry-failed').click(function(e) {
        e.preventDefault(); 
        window.location.href = window.location.href;
    });

    // tombol untuk reload speedtest
    $('#refresh-speed').click(function(e){
        e.preventDefault(); 
        reloadOokla();
        // window.location.href = window.location.href;
    })

    //untuk me listen hasil dari speedtest
    if (window.addEventListener) {
        window.addEventListener('message', ooklaListener);
    } else if (window.attachEvent) {
        window.attachEvent('onmessage', ooklaListener);
    }

    //tombol search pada halaman input tiket
    $('#submit-ticket').click(function(e) {
        e.preventDefault();
        if(!$('#ticket-search').val()) return $('.alert-del').removeClass('hidden');
        $('.alert-del').addClass('hidden');
        $('#ticket-search').val($('#ticket-search').val().toUpperCase());
        $('#submit-ticket').addClass('hidden')
        $('#loader-ticket').removeClass('hidden')
        createTask()
    });

}) 

/*
fungsi untuk membatasi tombol reload speedtest
*/
var count = 0;
function reloadOokla(){
	count++;

	let serverId = $('#select-serverId').val()
    let serverDst = null;
    if($('#select-serverId').val()){
        switch (serverId) {
            case '45466':
                    serverDst = '45466';
                break;
            case '37343':
                    serverDst = '37343';
                break;
            case '45462':
                    serverDst = '37343';
                break;
            case '45463':
                    serverDst = '45463';
                break;
            case '37344':
                    serverDst = '37344';  
                break;
            case '45464':
                serverDst = '45464';  
                break;
            case '45465':
                serverDst = '45464';  
        }

        $('#ookla').attr("src", `http://test-inf-1.speedtestcustom.com?serverId=${serverDst}`);
    }else{
        $('#ookla').attr("src", $('#ookla').attr("src"));
    }

	console.log(count);
	if (count > 10){
	document.getElementById("refresh-speed").disabled = true;
	$('#refresh-speed').addClass('hidden');
    $('#select-serverId').addClass('hidden');
	}
}
/*
untuk validasi menggunakan jaringan IndiHome atau tidak
*/
function ValidateAccess() {
    $.ajaxSetup({
        headers: {
            'X-CSRF-TOKEN': $('meta[name="csrf-token"]').attr('content')
        }
    });
    $.ajax({
        type: 'POST',
        url: '/check/validate',
        // `{{ url('/dashboard/searchLog') }}`,
        data: {
            // _token: _token,
            // public: public
        },
        dataType: 'json',
        async: true,
        tryCount: 0,
		retryLimit: 5,
        timeout: 60000,
        success: function(data) {
            if (data.token != true) {
                window.scrollTo({
                    top: 0,
                    behavior: 'smooth'
                });
                $('#allowed-access').addClass('hidden')
                $('#not-allowed-access').removeClass('hidden')
                $('#remote_addr').text(data.remote_addr);
            } else {
                window.scrollTo({
                    top: 0,
                    behavior: 'smooth'
                });
                
                $('#section_tracking').removeClass('hidden')
                $('#remote_addr').text(data.remote_addr);
                $('#allowed-access').removeClass('hidden')
                $('#section_validate').addClass('hidden')
                $('#title-page').removeClass('hidden')
            }
        },
        error: function(xhr, desc, e) {
            console.log(xhr);
        },
    });
}
/*
untuk menangkap hasil speedtest
*/
function ooklaListener(ev) {
    if (ev.data.download) {
        ev.data['speedtestName'] = "ookla"
        flag_speed = true
        autoSave = setInterval(() => {
            if (flag_redaman == true && flag_speed == true && flagPcrf == true) {
                 SaveSpeed(ev.data);
                if (flag_save == true) {
                    clearInterval(autoSave);
                    timeoutSave = setTimeout(() => {
                        clearInterval(autoSave);
                    }, 1000);
                }
            } else {
                console.log('task not found')
            }
        }, 1000);
        return
    }else{
        if(ev.data.success){
            ev.data['speedtestName'] = "mysiis"
    
            flag_speed = true
            autoSave = setInterval(() => {
                if (flag_redaman == true && flag_speed == true && flagPcrf == true) {
                     SaveSpeed(ev.data);
                    if (flag_save == true) {
                        clearInterval(autoSave);
                        timeoutSave = setTimeout(() => {
                            clearInterval(autoSave);
                        }, 1000);
                    }
                } else {
                    console.log('task not found')
                }
            }, 1000);
            return
        }else{
            flag_speed = true
            ev.data['speedtestName'] = "mysiis"
            return SaveSpeed(ev.data);
            // return doOokla()
        }
    }
}  
/*
untuk membuat task/transaction baru
*/
function createTask() {
    $.ajax({
        type: 'POST',
        contentType: 'application/json',
        dataType: 'JSON',
        url: urlbackend+'CreateTask',
        data: JSON.stringify({
            ticket: $('#ticket-search').val().split(' ').join('')
        }),
        async: true,
        tryCount: 0,
		retryLimit: 5,
        timeout: 60000,
        success: function(data) {
            ticket = $('#ticket-search').val()
            if (data.success == true) {
                $('#section_result').removeClass('hidden');
                $('#uuid').text(data.uid);
                $('#uuid-speed').text(data.uid);
                $('#uuid-footer').text(data.uid);
                $('#uuid-nav').text(data.uid);
                $('#trx-nav').removeClass('hidden')
                uuid = data.uid;
                return getAuth();
            } else{
                console.log(data)
                return failedWordingCreateTask()
            }
        },
        error: function(xhr, desc, e) {
            if (xhr.status != 200) {
				this.tryCount++;
				if (this.tryCount <= this.retryLimit) {
					//try again
					$.ajax(this);
					return;
				}
			} 

            if(xhr.statusText == 'timeout'){
                return failedWordingCreateTask()
                
            }
            console.log(xhr);

            return failedWordingCreateTask()
        },
    });
}
/*
generate authentikasi untuk request api berikutnya
*/
function getAuth() {
    $.ajax({
        type: 'post',
        url: urlbackend+'RetrieveAuth',
        data: {
            uuid: uuid,
        },
        async: true,
        tryCount: 0,
		retryLimit: 5,
        timeout: 60000, //1 Minute
        success: function(data) {
            $('#uuid-nav').addClass('hidden');
            if(data.success == true) {
                
                flagToken = true;
                return getND()
            } else {
                //call wording failed
                return failedWordingAuthentikasi()
            }
        },
        error: function(xhr){
            if (xhr.status != 200) {
				this.tryCount++;
				if (this.tryCount <= this.retryLimit) {
					//try again
					$.ajax(this);
					return;
				}
			} 

            if(xhr.statusText == 'timeout'){
                //call wording failed
                return failedWordingAuthentikasi()
            }
            console.log(xhr.status);

            //call wording failed
            return failedWordingAuthentikasi()
        }
    })
}
/*
untuk mencari service number (nd)
*/
function getND() {
    $.ajax({
        type: 'post',
        url: urlbackend+'RetrieveND',
        data: {
            uuid: $("#uuid-nav").html(),
            ticket: ticket
        },
        async: true,
        tryCount: 0,
		retryLimit: 5,
        timeout: 60000,
        success: function(data) {
            if(data.statusCode == 200){
                if (data.success == true) {
                    serviceNumber = data.nd
                    flagNd = true;
                    return getProfile()
                } else {
                    if(ticket.substr(0,3) == 'INC'){
                        return failedWordingGetNdTicketInsera()
                    }else{
                        return failedWordingGetNdTicketNossa()
                    }
                }
            }else{
                if(ticket.substr(0,3) == 'INC'){
                    return failedWordingErrorInsera()
                }else{
                    return failedWordingErrorNossa()
                }
            }
        },
        error: function(xhr){
            if (xhr.status != 200) {
				this.tryCount++;
				if (this.tryCount <= this.retryLimit) {
					//try again
					$.ajax(this);
					return;
				}
			} 
            console.log(xhr.status);
            if(ticket.substr(0,3) == 'INC'){
                return failedWordingErrorInsera()
            }else{
                return failedWordingErrorNossa()
            }
        }
    })
}

/*
untuk mendapatkan semua informasi paket 
*/
function getProfile() {
    $.ajax({
        type: 'post',
        url: urlbackend+'RetrieveProfile',
        data: {
            uuid: $("#uuid-nav").html(),
        },
        async: true,
        tryCount: 0,
		retryLimit: 5,
        timeout: 60000,
        success: function(data) {
            if (data.success == true) {
                if(data.speedtest > 0){
                    doOokla()
                }else{
                    // doOokla()
                    doDbt()
                }

                flagPcrf = true;
                $('html, body').animate({
                    scrollTop: $("#trx-nav").offset().top
                }, 300);
                $('#section_success').html(data.view);
                
                return getIPRadius()
            }else{
               return failedWordingErrorPcrf()
            }
        },
        error: function(xhr){
            if (xhr.status != 200) {
				this.tryCount++;
				if (this.tryCount <= this.retryLimit) {
					//try again
					$.ajax(this);
					return;
				}
			} 

            return failedWordingErrorPcrf()
        }
    })
}

/*
untuk mendapatkan IP origin dari service number (ND)
*/
function getIPRadius() {
    $.ajax({
        type: 'post',
        url: urlbackend+'RetrieveIP',
        data: {
            uuid: $("#uuid-nav").html(),
        },
        async: true,
        tryCount: 0,
		retryLimit: 5,
        timeout: 60000,
        success: function(data) {
            if(data.statusCode == 200){
                if (data.success == true) {
                    // console.log(data)
                    
                    flagRadius = true;
                    return getMyIP()
                }else {
                   return failedWordingIpNotFoundRadius()
                }
            }else{
               return failedWordingErrorRadius()
            }
        },
        error: function(xhr){
            if (xhr.status != 200) {
				this.tryCount++;
				if (this.tryCount <= this.retryLimit) {
					//try again
					$.ajax(this);
					return;
				}
			} 
            console.log(xhr);
            return failedWordingErrorRadius()
        }
    })
}

/*
untuk deteksi IP pada perangkat yang terhubung
 */
function getMyIP() {
    const url = 'https://myip.tacc.id';

    return fetch(url)
        .then(response => response.json())
        .then(data1 => {
            // JANGAN simpan ip_addr ke variable global atau tampilkan di console
            if (!data1.ip_addr) {
                alert('Gagal dapatkan IP');
                return Promise.reject('ip_addr not found');
            }

            const _token = $('meta[name="csrf-token"]').attr('content');
            const uuid = document.getElementById("uuid-nav").innerHTML;
            const url1 = urlbackend + 'SaveMyIP';

            return fetch(url1, {
                method: 'POST',
                body: JSON.stringify({ uuid, _token, ip_token: btoa(data1.ip_addr) }),
                headers: {
                    'Content-Type': 'application/json; charset=UTF-8',
                    'X-CSRF-TOKEN': _token
                }
            });
        })
        .then(() => {
            return checkIPValidation(document.getElementById("uuid-nav").innerHTML);
        })
        .catch(error => {
            alert('failed to open myip: ' + error);
            return failedWordingErrorMyip();
        });
}

let ipValidationToken = '';

function checkIPValidation(uuid) {
    const urlCheck = urlbackend + 'CheckIPValidation';
    let _token = $('meta[name="csrf-token"]').attr('content');

    return fetch(urlCheck, {
        method: 'POST',
        body: JSON.stringify({ uuid, _token }),
        headers: {
            'Content-Type': 'application/json; charset=UTF-8',
            'X-CSRF-TOKEN': _token
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            flagMyIp = true;
            ipValidationToken = data.token; // simpan token validasi IP

            $("#section_tracking").addClass('hidden');
            $('html, body').animate({
                scrollTop: $("#result-check").offset().top
            }, 500);
            $('#section_tracking_result').removeClass('hidden');
            $('#result-ticket').text(data.ticket);
            $('#result-nd').text(data.nd);
            $('#result-ts').text(data.ts + " WIB");
            $('#uuid-nav').addClass('hidden');

            return getRedaman(); // lanjutkan proses
        } else {
            return failedWordingIpNotMatch();
        }
    });
}

function getRedaman() {
    $.ajax({
        type: 'post',
        url: urlbackend+'RetrieveUkur',
        data: {
            uuid: $("#uuid-nav").html(),
            token: ipValidationToken // kirim token validasi IP ke backend
        },
        async: true,
        tryCount: 0,
        retryLimit: 5,
        timeout: 60000,
        success: function(data) {
            if (data.success == true) {
                $('#loader-redaman').addClass('hidden')
                flag_redaman = true
                if (data.redaman_passed == 1) {
                    $('#result-redaman').text('Layak');
                } else {
                    $('#result-redaman').text('Belum Layak');
                }
                return
            } else {
                return failedWordingErrorRedaman()
            }
        },
        error: function(xhr){
            if (xhr.status != 200) {
                this.tryCount++;
                if (this.tryCount <= this.retryLimit) {
                    //try again
                    $.ajax(this);
                    return;
                }
            } 

            return failedWordingErrorRedaman()
        }
    })
}
/*
untuk menyimpan hasil speedtest 
 */
function SaveSpeed(result) {
    clearInterval(autoSave);
    $.ajax({
        method: 'POST',
        dataType: 'json',
        url: urlbackend + 'SaveSpeed',
        contentType: 'application/json',
        data: JSON.stringify({
            'uuid': $("#uuid-nav").html(),
            'data': result
        }),
        headers: {
            'X-CSRF-TOKEN': $('meta[name="csrf-token"]').attr('content')
        },
        cache: false,
        async: true,
        tryCount: 0,
        retryLimit: 5,
        timeout: 60000,
        success: function(data) {
            // console.log(data.status)
            $('#refresh-speed').addClass('hidden');
            $('#select-serverId').addClass('hidden');
            clearTimeout(timeoutSave);
            flag_save = true;
            if (data.status == true) {
                $('#loader-speed').addClass('hidden');
                $('html, body').animate({
                    scrollTop: $("#uuid").offset().top
                }, 500);

                if (data.passed == 1) {
                    $('#result-speed').text('Layak');
                } else {
                    $('#result-speed').text('Belum Layak');
                }
                return getClosed();
            } else {
                $('#loader-speed').addClass('hidden');
                $('html, body').animate({
                    scrollTop: $("#uuid").offset().top
                }, 500);

                $('#result-speed').text('Failed');
                //    return failedWordingErrorSpeedtest()
            }
            return getClosed();
        },
        error: function(xhr) {
            if (xhr.status != 200) {
                this.tryCount++;
                if (this.tryCount <= this.retryLimit) {
                    //try again
                    $.ajax(this);
                    return;
                }
            }
            console.log(xhr);
            alert(xhr.responseText);
            return failedWordingErrorSpeedtest();
        }
    });
}

/*
untuk mendapatakan hasil dari pengujian
*/
function getClosed() {
    $('#section_tracking_result_information').addClass('hidden');
    $('#wording-closing-success').addClass('hidden');
    $('#btn-closing-success').addClass('hidden');
    $('#wording-closing-failed').addClass('hidden');
    $('#wording-closing-odp-failed').addClass('hidden');
    $('#btn-closing-failed').addClass('hidden');
	$('#wording-closing-speed-failed').addClass('hidden');

    $.ajax({
        type: 'post',
        url: urlbackend + 'RetrieveClose',
        data: {
            uuid: document.getElementById("uuid-nav").innerHTML
        },
        async: true,
        tryCount: 0,
        retryLimit: 5,
        success: function(data) {
            $('#loader-distance').addClass('hidden');
            $('html, body').animate({
                scrollTop: $("#uuid").offset().top
            }, 500);

            $('#loader-result').addClass('hidden');

            // Menampilkan nilai odp_distance
            var odpDistance = data.odp_distance !== null ? data.odp_distance : 0;
            $('#result-distance').text(odpDistance + ' m');

            // Menampilkan hasil berdasarkan status passed
            if (data.passed == 1) {
                $('#section_tracking_result_information').removeClass('hidden');
                $('#wording-closing-success').removeClass('hidden');
                $('#btn-closing-success').removeClass('hidden');
            } else if (data.passed == 2) {
                $('#section_tracking_result_information').removeClass('hidden');
                $('#wording-closing-speed-failed').removeClass('hidden');
                $('#btn-closing-success').removeClass('hidden');
            } else {
                // Jika failed dan odpDistance > 1000, tampilkan wording khusus
                if (odpDistance > 1000) {
                    $('#section_tracking_result_information').removeClass('hidden');
                    $('#wording-closing-odp-failed').removeClass('hidden');
                    $('#btn-closing-failed').removeClass('hidden');
                } else {
                    // Jika failed karena alasan lain
                    $('#section_tracking_result_information').removeClass('hidden');
                    $('#wording-closing-failed').removeClass('hidden');
                    $('#btn-closing-failed').removeClass('hidden');
                }
            }
        },
        error: function(xhr) {
            if (xhr.status != 200) {
                this.tryCount++;
                if (this.tryCount <= this.retryLimit) {
                    // Try again
                    $.ajax(this);
                    return;
                }
            }
            console.log(xhr.statusText);
        }
    });
}

function doOokla(){
    $('#select-serverId').addClass('hidden');
    $('#ookla').attr("src","https://test-inf-1.speedtestcustom.com");
	VarSpeed = 1;
}
/*
request param untuk call speedtest Mysiis - DBT
*/
function doDbt(){
    $('#select-serverId').addClass('hidden');
    $.ajax({
        type: 'post',
        url: urlbackend+'speedtest',
        data: {
            uuid: document.getElementById("uuid-nav").innerHTML,
            service: serviceNumber
        },
        async: true,
        tryCount: 0,
		retryLimit: 5,
        timeout: 60000,
        success: function(data) {
            $('#ookla').attr("src",`https://speedtest-r-ebis.mysiis.io/?v=${new Date().getTime()}&query=${data.param}`)
        },
        error: function(e){
            alert('Please try again!')
            // doOokla()
        }
    })
}

// Wording Failed ----------------------------------------------------------------------------------//

//failed create transaction
function failedWordingCreateTask(){
    $('#section_tracking').addClass('hidden')
    $('#section_tracking_result').removeClass('hidden')
    $('#section_result').addClass('hidden')
    $('#section_error').removeClass('hidden')
    $('#messages-error').text('Failed, Silahkan lakukan ulang dan input-kan ticket dengan benar')
}

//failed function get token
function failedWordingAuthentikasi(){
    $('#section_tracking').addClass('hidden')
    $('#section_tracking_result').removeClass('hidden')
    $('#section_result').addClass('hidden')
    $('#section_error').removeClass('hidden')
    $('#messages-error').text('tidak mendapatkan Authentikasi dari APIGW')
}


/*
    wording ketika dapat balikan tapi Service Number tidak ada
*/
function failedWordingGetNdTicketNossa(){
    $('#section_tracking').addClass('hidden')
    $('#section_tracking_result').removeClass('hidden')
    $('#section_result').addClass('hidden')
    $('#section_error').removeClass('hidden')
    $('#messages-error').text('Nomor internet tidak ditemukan dari Nossa')
}

/*
    wording ketika dapat balikan tapi Service Number tidak ada
*/
function failedWordingGetNdTicketInsera(){
    $('#section_tracking').addClass('hidden')
    $('#section_tracking_result').removeClass('hidden')
    $('#section_result').addClass('hidden')
    $('#section_error').removeClass('hidden')
    $('#messages-error').text('Nomor internet tidak ditemukan dari Insera')
}

function failedWordingErrorNossa(){
    $('#section_tracking').addClass('hidden')
    $('#section_tracking_result').removeClass('hidden')
    $('#section_result').addClass('hidden')
    $('#section_error').removeClass('hidden')
    $('#messages-error').text('Output dari Nossa tidak ditemukan')
}

function failedWordingErrorInsera(){
    $('#section_tracking').addClass('hidden')
    $('#section_tracking_result').removeClass('hidden')
    $('#section_result').addClass('hidden')
    $('#section_error').removeClass('hidden')
    $('#messages-error').text('Output dari Insera tidak ditemukan')
}

function failedWordingIpNotFoundRadius(){
    $('#section_tracking').addClass('hidden')
    $('#section_tracking_result').removeClass('hidden')
    $('#section_result').addClass('hidden')
    $('#section_error').removeClass('hidden')
    $('#messages-error').text('Tidak mendapatkan IP dari Radius')
}

function failedWordingErrorRadius(){
    $('#section_tracking').addClass('hidden')
    $('#section_tracking_result').removeClass('hidden')
    $('#section_result').addClass('hidden')
    $('#section_error').removeClass('hidden')
    $('#messages-error').text('Output dari Radius tidak ditemukan')
}

function failedWordingIpNotMatch(){
    $('#section_tracking').addClass('hidden')
    $('#section_tracking_result').removeClass('hidden')
    $('#section_result').addClass('hidden')
    $('#section_error').removeClass('hidden')
    $('#messages-error').text('Terindikasi tidak di jaringan Indihome pelanggan')
}

function failedWordingErrorMyip(){
    $('#section_tracking').addClass('hidden')
    $('#section_tracking_result').removeClass('hidden')
    $('#section_result').addClass('hidden')
    $('#section_error').removeClass('hidden')
    $('#messages-error').text('output dari MyIP tidak ditemukan')
}

function failedWordingErrorRedaman(){
    $('#section_result').addClass('hidden');
    $('#section_error').removeClass('hidden')
    $('#messages-error').text('Redaman tidak ditemukan pada iBooster')
}

function failedWordingErrorPcrf(){
    $('#section_tracking').addClass('hidden')
    $('#section_tracking_result').removeClass('hidden')
    $('#section_result').addClass('hidden');
    $('#section_error').removeClass('hidden')
    $('#messages-error').text('Paket tidak ditemukan dari PCRF')
}

function failedWordingErrorSpeedtest(){
    $('#section_result').addClass('hidden');
    $('#section_error').removeClass('hidden')
    $('#messages-error').text('result speedtest tidak di temukan') 
}

//--------------------------------------------------------------------------------------------------//

