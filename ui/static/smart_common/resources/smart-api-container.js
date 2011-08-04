/*
 * The SMART container side of the API
 * Josh Mandel
 * Ben Adida
 */

(function(window) {

// simple pattern to match URLs with http or https
var __SMART_URL_PATTERN = /^(https?:\/\/[^/]+)/;

// extract a postMessage appropriate origin from a URL
function __SMART_extract_origin(url) {
    var match = url.match(__SMART_URL_PATTERN);
    if (match)
	return match[1].toLowerCase();
    else
	return null;
}


window.SMART_CONTAINER = function(SMART_HELPER) {
    
    var sc = this;
    sc.debug = false;
    sc.SMART_HELPER = SMART_HELPER;
    sc.running_apps = {};
    sc.running_apps.callbacks = {};

    var generate_ready_message = function(app_instance, callback) {	    
	var message = { context: app_instance.context,
			credentials: app_instance.credentials,
			uuid: app_instance.uuid,
			ready_data: app_instance.ready_data
		      };
	
	return message;
    };

    var get_manifest_wrapper = function(app_instance) {
	var dfd = $.Deferred();
	SMART_HELPER.get_manifest(app_instance, function(r) {
	    app_instance.manifest = r;
	    dfd.resolve(app_instance);
	});
	return dfd.promise();
    };
    
    var get_credentials_wrapper = function(app_instance) {
	var dfd = $.Deferred();
	SMART_HELPER.get_credentials(app_instance, function(r) {
	    app_instance.credentials = r;
	    dfd.resolve(app_instance)
	});
	return dfd.promise();
    };

    var get_iframe_wrapper = function(app_instance) {
	var dfd = $.Deferred();
	SMART_HELPER.get_iframe(app_instance, function(r) {
	    app_instance.iframe = r;
	    dfd.resolve(app_instance)
	});
	return dfd.promise();
    };


    var receive_api_call = function(app_instance, call_info, callback) {
	sc.SMART_HELPER.handle_api(app_instance, 
				     call_info, 
				     function(r){
					 callback({
					     contentType: "text",  
					     data: r})
				     });	    
    };

    var bind_emr_frame_app_channel = function(app_instance) {
	    app_instance.channel.bind("api_call_delegated", function(t, p) {
		t.delayReturn(true);
		var on_behalf_of = sc.running_apps[p.originating_app_uuid];
		var call_info = p.call_info;
		
		receive_api_call(on_behalf_of, call_info, t.complete); 
	    });

	    app_instance.channel.bind("launch_app", function(t, p) {
		t.delayReturn(true);

		var new_app_instance = p;

		get_manifest_wrapper(new_app_instance)
		    .pipe(get_credentials_wrapper)
		    .pipe(function() {
			var uuid = new_app_instance.uuid;
			console.log(sc.running_apps);

			if (sc.running_apps[uuid])
			    throw "Can't launch app that's already launched: " + uuid;
			sc.running_apps[uuid] = new_app_instance;
			
			t.complete(new_app_instance);
		    });
	    });
    };

    var bind_ui_app_channel = function(app_instance) {
	    app_instance.channel.bind("call_app_and_wait", function(t, p) {
		t.delayReturn(true);
		receive_call_app_and_wait(app_instance, p, t.complete);
	    });
    };

    var bind_app_channel = function(app_instance) {

	app_instance.channel.bind("api_call", function(t, p) {
	    t.delayReturn(true);
	    receive_api_call(app_instance, p, t.complete);
	});
	
    };

    // Once an app launches, discover which iframe it belongs to,
    // and create a new jschannel bound to that iframe.
    // If necessary, bind functions to the channel according to app type.
    var bind_new_channel = function(app_instance) {
	
	app_instance.channel && app_instance.channel.destroy();
	
	app_instance.channel  = Channel.build({
	    window: app_instance.iframe.contentWindow, 
	    origin: app_instance.origin, 
	    scope: app_instance.uuid, 
	    debugOutput: sc.debug
	});
	
	bind_app_channel(app_instance);
	
	if (app_instance.manifest.mode == "ui")// "emr_frame") // TODO:  rever this to emrframe.
	    bind_emr_frame_app_channel(app_instance);
	
	if (app_instance.manifest.mode == "ui")
	    bind_ui_app_channel(app_instance);

	var ready_data = generate_ready_message(app_instance);

	app_instance.channel.notify({
		method: "ready",
		params: ready_data
	});

    };

    var procureChannel = function(event){
	var app_instance = null;
	if (event.data !== '"procure_channel"') return;

	$.each(sc.running_apps, function(aid, a) {
	    if (a.iframe && a.iframe.contentWindow === event.source)
		app_instance = a;
	});
	
	if (app_instance) {
	    bind_new_channel(app_instance);
	    event.source.postMessage('"app_instance_uuid='+app_instance.uuid+'"', app_instance.origin);
	}
    };

    if (window.addEventListener) window.addEventListener('message', procureChannel, false);
    else if(window.attachEvent) window.attachEvent('onmessage', procureChannel);

    sc.context_changed = function() {
    	jQuery.each(sc.running_apps, function(aid, a){
    	    var c = a.channel;
    	    if (c)  {
		console.log(aid);
        	c.notify({method: "destroy"});
    		c.destroy();
    	    }
	    if (a.iframe)
	    {
		$(a.iframe).remove();
	    }
    	});
	
	sc.running_apps = {};	    

	if (typeof SMART_HELPER.handle_context_changed == "function")
	    SMART_HELPER.handle_context_changed();
    };

    sc.notify_app_foregrounded= function(app_instance_id){
    	var app_instance = sc.running_apps[app_instance_id];
	if (app_instance.channel !== undefined)
	    app_instance.channel.notify({method: "foreground"});
    };

    sc.notify_app_backgrounded = function(app_instance_id){
    	var app_instance = sc.running_apps[app_instance_id];
	if (app_instance.channel !== undefined)
	    app_instance.channel.notify({method: "background"});
    };


    sc.notify_app_destroyed = function(app_instance_id){
    	var app_instance = sc.running_apps[app_instance_id];
	if (app_instance.channel !== undefined)
	    app_instance.channel.notify({method: "destroy"});
    };
  
    sc.launch_app = function(app_descriptor, context, called_by, input_data) {

	if (typeof app_descriptor !== "string") {
	    throw "Expected an app descriptor string!";
	}
	
	var uuid = randomUUID();
	var app_instance = sc.running_apps[uuid] = {
	    uuid: uuid,
	    descriptor: app_descriptor,
	    context: context
	};

/* TODO: add this to a call_app handler
    	if (called_by) {
    	    running_apps.callbacks[uuid] = callback;
	    app_instance.called_by = called_by;
	    app_instance.ready_data = input_data;
    	}  
*/

	if (typeof SMART_HELPER.on_app_launch_begin == "function")
	    SMART_HELPER.on_app_launch_begin(app_instance);	

	get_manifest_wrapper(app_instance)
	    .pipe(get_credentials_wrapper)
	    .pipe(get_iframe_wrapper)
	    .pipe(function() {
		var launch_url = app_instance.manifest.activities.main;
		launch_url += "?"+app_instance.credentials.oauth_header;
		app_instance.origin = __SMART_extract_origin(launch_url);
		app_instance.iframe.src = launch_url;
		if (typeof SMART_HELPER.on_app_launch_complete == "function")
		    SMART_HELPER.on_app_launch_complete(app_instance);
	    });	
    };    
};

function randomUUID() {
	var s = [], itoh = '0123456789ABCDEF';
	// Make array of random hex digits. The UUID only has 32 digits in it, but
	// we
	// allocate an extra items to make room for the '-'s we'll be inserting.
	for ( var i = 0; i < 36; i++)
		s[i] = Math.floor(Math.random() * 0x10);
	// Conform to RFC-4122, section 4.4
	s[14] = 4; // Set 4 high bits of time_high field to version
	s[19] = (s[19] & 0x3) | 0x8; // Specify 2 high bits of clock sequence
	// Convert to hex chars
	for ( var i = 0; i < 36; i++)
		s[i] = itoh[s[i]];
	// Insert '-'s
	s[8] = s[13] = s[18] = s[23] = '-';
	return s.join('');
};

})(window);