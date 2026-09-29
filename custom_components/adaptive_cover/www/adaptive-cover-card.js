/*! adaptive-cover-card v1.0.0 | MIT License | https://github.com/mrvollger/adaptive-cover-card */
function e(e,t,o,i){var s,n=arguments.length,r=n<3?t:null===i?i=Object.getOwnPropertyDescriptor(t,o):i;if("object"==typeof Reflect&&"function"==typeof Reflect.decorate)r=Reflect.decorate(e,t,o,i);else for(var a=e.length-1;a>=0;a--)(s=e[a])&&(r=(n<3?s(r):n>3?s(t,o,r):s(t,o))||r);return n>3&&r&&Object.defineProperty(t,o,r),r}"function"==typeof SuppressedError&&SuppressedError;const t=globalThis,o=t.ShadowRoot&&(void 0===t.ShadyCSS||t.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,i=Symbol(),s=new WeakMap;let n=class{constructor(e,t,o){if(this._$cssResult$=!0,o!==i)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o;const t=this.t;if(o&&void 0===e){const o=void 0!==t&&1===t.length;o&&(e=s.get(t)),void 0===e&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),o&&s.set(t,e))}return e}toString(){return this.cssText}};const r=(e,...t)=>{const o=1===e.length?e[0]:t.reduce((t,o,i)=>t+(e=>{if(!0===e._$cssResult$)return e.cssText;if("number"==typeof e)return e;throw Error("Value passed to 'css' function must be a 'css' function result: "+e+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(o)+e[i+1],e[0]);return new n(o,e,i)},a=o?e=>e:e=>e instanceof CSSStyleSheet?(e=>{let t="";for(const o of e.cssRules)t+=o.cssText;return(e=>new n("string"==typeof e?e:e+"",void 0,i))(t)})(e):e,{is:l,defineProperty:c,getOwnPropertyDescriptor:d,getOwnPropertyNames:h,getOwnPropertySymbols:u,getPrototypeOf:p}=Object,g=globalThis,m=g.trustedTypes,f=m?m.emptyScript:"",_=g.reactiveElementPolyfillSupport,v=(e,t)=>e,y={toAttribute(e,t){switch(t){case Boolean:e=e?f:null;break;case Object:case Array:e=null==e?e:JSON.stringify(e)}return e},fromAttribute(e,t){let o=e;switch(t){case Boolean:o=null!==e;break;case Number:o=null===e?null:Number(e);break;case Object:case Array:try{o=JSON.parse(e)}catch(e){o=null}}return o}},w=(e,t)=>!l(e,t),b={attribute:!0,type:String,converter:y,reflect:!1,useDefault:!1,hasChanged:w};Symbol.metadata??=Symbol("metadata"),g.litPropertyMetadata??=new WeakMap;let x=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=b){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(e,t),!t.noAccessor){const o=Symbol(),i=this.getPropertyDescriptor(e,o,t);void 0!==i&&c(this.prototype,e,i)}}static getPropertyDescriptor(e,t,o){const{get:i,set:s}=d(this.prototype,e)??{get(){return this[t]},set(e){this[t]=e}};return{get:i,set(t){const n=i?.call(this);s?.call(this,t),this.requestUpdate(e,n,o)},configurable:!0,enumerable:!0}}static getPropertyOptions(e){return this.elementProperties.get(e)??b}static _$Ei(){if(this.hasOwnProperty(v("elementProperties")))return;const e=p(this);e.finalize(),void 0!==e.l&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(v("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(v("properties"))){const e=this.properties,t=[...h(e),...u(e)];for(const o of t)this.createProperty(o,e[o])}const e=this[Symbol.metadata];if(null!==e){const t=litPropertyMetadata.get(e);if(void 0!==t)for(const[e,o]of t)this.elementProperties.set(e,o)}this._$Eh=new Map;for(const[e,t]of this.elementProperties){const o=this._$Eu(e,t);void 0!==o&&this._$Eh.set(o,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){const t=[];if(Array.isArray(e)){const o=new Set(e.flat(1/0).reverse());for(const e of o)t.unshift(a(e))}else void 0!==e&&t.push(a(e));return t}static _$Eu(e,t){const o=t.attribute;return!1===o?void 0:"string"==typeof o?o:"string"==typeof e?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),void 0!==this.renderRoot&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){const e=new Map,t=this.constructor.elementProperties;for(const o of t.keys())this.hasOwnProperty(o)&&(e.set(o,this[o]),delete this[o]);e.size>0&&(this._$Ep=e)}createRenderRoot(){const e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return((e,i)=>{if(o)e.adoptedStyleSheets=i.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(const o of i){const i=document.createElement("style"),s=t.litNonce;void 0!==s&&i.setAttribute("nonce",s),i.textContent=o.cssText,e.appendChild(i)}})(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,o){this._$AK(e,o)}_$ET(e,t){const o=this.constructor.elementProperties.get(e),i=this.constructor._$Eu(e,o);if(void 0!==i&&!0===o.reflect){const s=(void 0!==o.converter?.toAttribute?o.converter:y).toAttribute(t,o.type);this._$Em=e,null==s?this.removeAttribute(i):this.setAttribute(i,s),this._$Em=null}}_$AK(e,t){const o=this.constructor,i=o._$Eh.get(e);if(void 0!==i&&this._$Em!==i){const e=o.getPropertyOptions(i),s="function"==typeof e.converter?{fromAttribute:e.converter}:void 0!==e.converter?.fromAttribute?e.converter:y;this._$Em=i;const n=s.fromAttribute(t,e.type);this[i]=n??this._$Ej?.get(i)??n,this._$Em=null}}requestUpdate(e,t,o,i=!1,s){if(void 0!==e){const n=this.constructor;if(!1===i&&(s=this[e]),o??=n.getPropertyOptions(e),!((o.hasChanged??w)(s,t)||o.useDefault&&o.reflect&&s===this._$Ej?.get(e)&&!this.hasAttribute(n._$Eu(e,o))))return;this.C(e,t,o)}!1===this.isUpdatePending&&(this._$ES=this._$EP())}C(e,t,{useDefault:o,reflect:i,wrapped:s},n){o&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,n??t??this[e]),!0!==s||void 0!==n)||(this._$AL.has(e)||(this.hasUpdated||o||(t=void 0),this._$AL.set(e,t)),!0===i&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}const e=this.scheduleUpdate();return null!=e&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[e,t]of this._$Ep)this[e]=t;this._$Ep=void 0}const e=this.constructor.elementProperties;if(e.size>0)for(const[t,o]of e){const{wrapped:e}=o,i=this[t];!0!==e||this._$AL.has(t)||void 0===i||this.C(t,void 0,o,i)}}let e=!1;const t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(e=>e.hostUpdate?.()),this.update(t)):this._$EM()}catch(t){throw e=!1,this._$EM(),t}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return!0}update(e){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(e){}firstUpdated(e){}};x.elementStyles=[],x.shadowRootOptions={mode:"open"},x[v("elementProperties")]=new Map,x[v("finalized")]=new Map,_?.({ReactiveElement:x}),(g.reactiveElementVersions??=[]).push("2.1.2");const $=globalThis,k=e=>e,S=$.trustedTypes,A=S?S.createPolicy("lit-html",{createHTML:e=>e}):void 0,C="$lit$",E=`lit$${Math.random().toFixed(9).slice(2)}$`,M="?"+E,z=`<${M}>`,O=document,I=()=>O.createComment(""),T=e=>null===e||"object"!=typeof e&&"function"!=typeof e,F=Array.isArray,R="[ \t\n\f\r]",j=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,N=/-->/g,P=/>/g,D=RegExp(`>|${R}(?:([^\\s"'>=/]+)(${R}*=${R}*(?:[^ \t\n\f\r"'\`<>=]|("|')|))|$)`,"g"),K=/'/g,B=/"/g,W=/^(?:script|style|textarea|title)$/i,V=e=>(t,...o)=>({_$litType$:e,strings:t,values:o}),G=V(1),U=V(2),L=Symbol.for("lit-noChange"),Y=Symbol.for("lit-nothing"),H=new WeakMap,Q=O.createTreeWalker(O,129);function q(e,t){if(!F(e)||!e.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==A?A.createHTML(t):t}const X=(e,t)=>{const o=e.length-1,i=[];let s,n=2===t?"<svg>":3===t?"<math>":"",r=j;for(let t=0;t<o;t++){const o=e[t];let a,l,c=-1,d=0;for(;d<o.length&&(r.lastIndex=d,l=r.exec(o),null!==l);)d=r.lastIndex,r===j?"!--"===l[1]?r=N:void 0!==l[1]?r=P:void 0!==l[2]?(W.test(l[2])&&(s=RegExp("</"+l[2],"g")),r=D):void 0!==l[3]&&(r=D):r===D?">"===l[0]?(r=s??j,c=-1):void 0===l[1]?c=-2:(c=r.lastIndex-l[2].length,a=l[1],r=void 0===l[3]?D:'"'===l[3]?B:K):r===B||r===K?r=D:r===N||r===P?r=j:(r=D,s=void 0);const h=r===D&&e[t+1].startsWith("/>")?" ":"";n+=r===j?o+z:c>=0?(i.push(a),o.slice(0,c)+C+o.slice(c)+E+h):o+E+(-2===c?t:h)}return[q(e,n+(e[o]||"<?>")+(2===t?"</svg>":3===t?"</math>":"")),i]};class J{constructor({strings:e,_$litType$:t},o){let i;this.parts=[];let s=0,n=0;const r=e.length-1,a=this.parts,[l,c]=X(e,t);if(this.el=J.createElement(l,o),Q.currentNode=this.el.content,2===t||3===t){const e=this.el.content.firstChild;e.replaceWith(...e.childNodes)}for(;null!==(i=Q.nextNode())&&a.length<r;){if(1===i.nodeType){if(i.hasAttributes())for(const e of i.getAttributeNames())if(e.endsWith(C)){const t=c[n++],o=i.getAttribute(e).split(E),r=/([.?@])?(.*)/.exec(t);a.push({type:1,index:s,name:r[2],strings:o,ctor:"."===r[1]?ie:"?"===r[1]?se:"@"===r[1]?ne:oe}),i.removeAttribute(e)}else e.startsWith(E)&&(a.push({type:6,index:s}),i.removeAttribute(e));if(W.test(i.tagName)){const e=i.textContent.split(E),t=e.length-1;if(t>0){i.textContent=S?S.emptyScript:"";for(let o=0;o<t;o++)i.append(e[o],I()),Q.nextNode(),a.push({type:2,index:++s});i.append(e[t],I())}}}else if(8===i.nodeType)if(i.data===M)a.push({type:2,index:s});else{let e=-1;for(;-1!==(e=i.data.indexOf(E,e+1));)a.push({type:7,index:s}),e+=E.length-1}s++}}static createElement(e,t){const o=O.createElement("template");return o.innerHTML=e,o}}function Z(e,t,o=e,i){if(t===L)return t;let s=void 0!==i?o._$Co?.[i]:o._$Cl;const n=T(t)?void 0:t._$litDirective$;return s?.constructor!==n&&(s?._$AO?.(!1),void 0===n?s=void 0:(s=new n(e),s._$AT(e,o,i)),void 0!==i?(o._$Co??=[])[i]=s:o._$Cl=s),void 0!==s&&(t=Z(e,s._$AS(e,t.values),s,i)),t}class ee{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){const{el:{content:t},parts:o}=this._$AD,i=(e?.creationScope??O).importNode(t,!0);Q.currentNode=i;let s=Q.nextNode(),n=0,r=0,a=o[0];for(;void 0!==a;){if(n===a.index){let t;2===a.type?t=new te(s,s.nextSibling,this,e):1===a.type?t=new a.ctor(s,a.name,a.strings,this,e):6===a.type&&(t=new re(s,this,e)),this._$AV.push(t),a=o[++r]}n!==a?.index&&(s=Q.nextNode(),n++)}return Q.currentNode=O,i}p(e){let t=0;for(const o of this._$AV)void 0!==o&&(void 0!==o.strings?(o._$AI(e,o,t),t+=o.strings.length-2):o._$AI(e[t])),t++}}class te{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,o,i){this.type=2,this._$AH=Y,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=o,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode;const t=this._$AM;return void 0!==t&&11===e?.nodeType&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=Z(this,e,t),T(e)?e===Y||null==e||""===e?(this._$AH!==Y&&this._$AR(),this._$AH=Y):e!==this._$AH&&e!==L&&this._(e):void 0!==e._$litType$?this.$(e):void 0!==e.nodeType?this.T(e):(e=>F(e)||"function"==typeof e?.[Symbol.iterator])(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==Y&&T(this._$AH)?this._$AA.nextSibling.data=e:this.T(O.createTextNode(e)),this._$AH=e}$(e){const{values:t,_$litType$:o}=e,i="number"==typeof o?this._$AC(e):(void 0===o.el&&(o.el=J.createElement(q(o.h,o.h[0]),this.options)),o);if(this._$AH?._$AD===i)this._$AH.p(t);else{const e=new ee(i,this),o=e.u(this.options);e.p(t),this.T(o),this._$AH=e}}_$AC(e){let t=H.get(e.strings);return void 0===t&&H.set(e.strings,t=new J(e)),t}k(e){F(this._$AH)||(this._$AH=[],this._$AR());const t=this._$AH;let o,i=0;for(const s of e)i===t.length?t.push(o=new te(this.O(I()),this.O(I()),this,this.options)):o=t[i],o._$AI(s),i++;i<t.length&&(this._$AR(o&&o._$AB.nextSibling,i),t.length=i)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);e!==this._$AB;){const t=k(e).nextSibling;k(e).remove(),e=t}}setConnected(e){void 0===this._$AM&&(this._$Cv=e,this._$AP?.(e))}}let oe=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,o,i,s){this.type=1,this._$AH=Y,this._$AN=void 0,this.element=e,this.name=t,this._$AM=i,this.options=s,o.length>2||""!==o[0]||""!==o[1]?(this._$AH=Array(o.length-1).fill(new String),this.strings=o):this._$AH=Y}_$AI(e,t=this,o,i){const s=this.strings;let n=!1;if(void 0===s)e=Z(this,e,t,0),n=!T(e)||e!==this._$AH&&e!==L,n&&(this._$AH=e);else{const i=e;let r,a;for(e=s[0],r=0;r<s.length-1;r++)a=Z(this,i[o+r],t,r),a===L&&(a=this._$AH[r]),n||=!T(a)||a!==this._$AH[r],a===Y?e=Y:e!==Y&&(e+=(a??"")+s[r+1]),this._$AH[r]=a}n&&!i&&this.j(e)}j(e){e===Y?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}};class ie extends oe{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===Y?void 0:e}}class se extends oe{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==Y)}}class ne extends oe{constructor(e,t,o,i,s){super(e,t,o,i,s),this.type=5}_$AI(e,t=this){if((e=Z(this,e,t,0)??Y)===L)return;const o=this._$AH,i=e===Y&&o!==Y||e.capture!==o.capture||e.once!==o.once||e.passive!==o.passive,s=e!==Y&&(o===Y||i);i&&this.element.removeEventListener(this.name,this,o),s&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}}class re{constructor(e,t,o){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=o}get _$AU(){return this._$AM._$AU}_$AI(e){Z(this,e)}}const ae=$.litHtmlPolyfillSupport;ae?.(J,te),($.litHtmlVersions??=[]).push("3.3.2");const le=globalThis;let ce=class extends x{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){const t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=((e,t,o)=>{const i=o?.renderBefore??t;let s=i._$litPart$;if(void 0===s){const e=o?.renderBefore??null;i._$litPart$=s=new te(t.insertBefore(I(),e),e,void 0,o??{})}return s._$AI(e),s})(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return L}};ce._$litElement$=!0,ce.finalized=!0,le.litElementHydrateSupport?.({LitElement:ce});const de=le.litElementPolyfillSupport;de?.({LitElement:ce}),(le.litElementVersions??=[]).push("4.2.2");const he=e=>(t,o)=>{void 0!==o?o.addInitializer(()=>{customElements.define(e,t)}):customElements.define(e,t)},ue={attribute:!0,type:String,converter:y,reflect:!1,hasChanged:w},pe=(e=ue,t,o)=>{const{kind:i,metadata:s}=o;let n=globalThis.litPropertyMetadata.get(s);if(void 0===n&&globalThis.litPropertyMetadata.set(s,n=new Map),"setter"===i&&((e=Object.create(e)).wrapped=!0),n.set(o.name,e),"accessor"===i){const{name:i}=o;return{set(o){const s=t.get.call(this);t.set.call(this,o),this.requestUpdate(i,s,e,!0,o)},init(t){return void 0!==t&&this.C(i,void 0,e,t),t}}}if("setter"===i){const{name:i}=o;return function(o){const s=this[i];t.call(this,o),this.requestUpdate(i,s,e,!0,o)}}throw Error("Unsupported decorator location: "+i)};function ge(e){return(t,o)=>"object"==typeof o?pe(e,t,o):((e,t,o)=>{const i=t.hasOwnProperty(o);return t.constructor.createProperty(o,e),i?Object.getOwnPropertyDescriptor(t,o):void 0})(e,t,o)}function me(e){return ge({...e,state:!0,attribute:!1})}function fe(e,t,o){if(!e)return!0;for(const i of o)if(i&&e.states[i]!==t.states[i])return!0;return!1}const _e="1.0.0",ve="adaptive-cover-card",ye="adaptive-cover-card-editor",we="adaptive-cover-sky-compass-card",be="adaptive-cover-sky-compass-card-editor",xe="adaptive-cover-tile-card",$e="adaptive-cover-tile-card-editor",ke="adaptive-cover-decision-card",Se="adaptive-cover-decision-card-editor",Ae="adaptive-cover-house-card",Ce="adaptive-cover",Ee=`ll-strategy-dashboard-${Ce}`,Me="adaptive_cover",ze=["privacy","climate_open_heat","climate_block_heat","climate_tilt_preset","climate_default","admit_no_glare","shaded_by_overhang","sunset","calculated","default"],Oe={privacy:"Privacy",climate_open_heat:"Climate · warm up",climate_block_heat:"Climate · block heat",climate_tilt_preset:"Climate · tilt preset",climate_default:"Climate · default",admit_no_glare:"Warmth, no glare",shaded_by_overhang:"Shaded by overhang",sunset:"Sunset",calculated:"Sun tracking",default:"Default"},Ie={privacy:"handler.privacy",climate_open_heat:"handler.climate_open_heat",climate_block_heat:"handler.climate_block_heat",climate_tilt_preset:"handler.climate_tilt_preset",climate_default:"handler.climate_default",admit_no_glare:"handler.admit_no_glare",shaded_by_overhang:"handler.shaded_by_overhang",sunset:"handler.sunset",calculated:"handler.calculated",default:"handler.default"},Te={cover_blind:"mdi:blinds-horizontal",cover_awning:"mdi:awning-outline",cover_tilt:"mdi:blinds"},Fe={cover_blind:"mdi:blinds-open",cover_awning:"mdi:awning-outline",cover_tilt:"mdi:blinds-open"},Re={cover_blind:"mdi:blinds-horizontal-closed",cover_awning:"mdi:window-closed-variant",cover_tilt:"mdi:blinds"},je={calculated:"solar",admit_no_glare:"glare_zone",privacy:"privacy",sunset:"sunset",climate_open_heat:"climate",climate_block_heat:"climate",climate_tilt_preset:"climate",climate_default:"climate"},Ne={auto:{bg:"rgba(76, 175, 80, 0.18)",fg:"#2e7d32"},manual:{bg:"rgba(255, 152, 0, 0.22)",fg:"#e65100"},climate:{bg:"rgba(0, 150, 136, 0.22)",fg:"#00695c"},glare_zone:{bg:"rgba(244, 67, 54, 0.22)",fg:"#b71c1c"},privacy:{bg:"rgba(103, 58, 183, 0.22)",fg:"#4527a0"},sunset:{bg:"rgba(255, 112, 67, 0.22)",fg:"#bf360c"},solar:{bg:"rgba(76, 175, 80, 0.22)",fg:"#1b5e20"},off:{bg:"rgba(97, 97, 97, 0.28)",fg:"#212121"},off_schedule:{bg:"rgba(96, 125, 139, 0.22)",fg:"#37474f"}},Pe={auto:"badge.auto",manual:"badge.manual",climate:"badge.climate",glare_zone:"badge.glare_zone",privacy:"badge.privacy",sunset:"badge.sunset",solar:"badge.solar",off:"badge.off",off_schedule:"badge.off_schedule"},De={auto:"mdi:autorenew",manual:"mdi:hand-back-right",climate:"mdi:thermostat",glare_zone:"mdi:weather-sunny-alert",privacy:"mdi:shield-home",sunset:"mdi:weather-sunset-down",solar:"mdi:white-balance-sunny",off:"mdi:power",off_schedule:"mdi:clock-alert-outline"},Ke={integration_enabled:!0,automatic_control:!0,reset_manual_override:!0},Be={"sensor:Cover Position":"target_position_sensor","sensor:Start Sun":"start_sensor","sensor:End Sun":"end_sensor","sensor:Control Method":"control_status_sensor","binary_sensor:Sun Infront":"sun_infront_binary","binary_sensor:Manual Override":"manual_override_binary","switch:Toggle Control":"automatic_control_switch","switch:Manual Override":"manual_toggle_switch","switch:Climate Mode":"climate_mode_switch","button:Reset Manual Override":"reset_override_button"},We={handler:{privacy:"Privacy",climate_open_heat:"Climate · warm up",climate_block_heat:"Climate · block heat",climate_tilt_preset:"Climate · tilt preset",climate_default:"Climate · default",admit_no_glare:"Warmth, no glare",shaded_by_overhang:"Shaded by overhang",sunset:"Sunset",calculated:"Sun tracking",default:"Default"},badge:{auto:"Auto",manual:"Manual",climate:"Climate",glare_zone:"No glare",privacy:"Privacy",sunset:"Sunset",solar:"Solar tracking",off:"Off",off_schedule:"Off-schedule"},forecast:{event:{calculated:"Sun tracking begins",default:"Default position",sunset:"Sunset position",privacy:"Privacy position"},hover_hint:"Hover the curve for time + forecast position; hover a colored line for the intent change it marks.",solar_only_note:"Forecast assumes current temperature/presence/weather persist — manual overrides are not reflected."},dialog:{window_settings:"Window settings",open_device_page:"Open device page",close:"Close",target:"Target",resume_auto:"Resume Auto",hide_advanced:"▼ Hide advanced",show_advanced:"▶ Advanced",on:"On",off:"Off",controls:"Controls",automatic:"Automatic",climate:"Climate",manual_detection:"Manual detection",toggle_hint:"{label} {state} — tap to toggle",state_on:"on",state_off:"off",todays_forecast:"Today's forecast",last_moves:"Recent moves",move_blocked:"move blocked by {gate}"},overrides:{title:"Overrides",manual:"Manual",active:"Active",off:"Off",ends_in:"ends in {time}",active_count:"{count} active",timeout:"expires in {time}",reset_manual:"Return to Auto",resume_confirm:"Resume automatic control? This shade will move back to its automatic position.",resume_confirm_pos:"Resume automatic control? This shade will move to {position}% now."},climate:{title:"Climate",active:"Active: {strategy}",indoor:"Indoor",outdoor:"Outdoor",presence:"Presence",sunny:"Sunny",lux:"Lux",irradiance:"Irradiance",mode_off:"Climate mode off",standby:"Standby",threshold_low:"low",threshold_high:"high",threshold_summer_outside:"summer",reason:{outside_time_window:"Outside the operating time window",thresholds_not_met:"Temperatures within the comfort band — no action needed",other_mode_active:"Another control mode is currently active",readings_unavailable:"Temperature readings unavailable",mode_off:"Climate mode is turned off"}},compass:{placeholder_no_entries:"No Adaptive Cover entries selected.",placeholder_no_sun:"Sun sensor not yet populated.",sun_tooltip:"Sun: {az} az / {el} el",sunrise_tooltip:"Sunrise: {time}",sunset_tooltip:"Sunset: {time}",moon_tooltip:"Moon: {phase} ({pct}%)",sun_path_tooltip:"Sun path (today)",in_fov_check:"✓ in FOV",in_fov:"in FOV",in_fov_tooltip:"Sun is currently within this window’s field of view",none:"—",sun:"Sun",moon:"Moon",sun_up_not_hitting:"Sun (up, not hitting)",sun_below_horizon:"Sun (below horizon)",window_fov:"Window FOV",sun_path:"Sun path",sunrise:"Sunrise",sunset:"Sunset",cover_target:"Cover target",cover_held:"Cover position (held)",window_normal:"Window azimuth",stat_sun:"Sun: ",stat_azi:"Azi: ",stat_elev:"Elev: ",stat_window:"Window: ",active_sun_arc:"Active sun arc {from} – {to}{elev}",fov_arc:"FOV {left} left / {right} right{elev}",window_normal_tooltip:"Window azimuth: {bearing}",cover_position_target:"Target: {pct}%",cover_position_target_awning:"Target (extended): {pct}%",cover_position_actual:"Actual: {pct}%",blind_spot:"Blind spot: {from} – {to}",elev_suffix:" · elev {min}–{max}"},covers:{placeholder:"No covers reported by the integration.",title:"Covers",target:"Target: {pct}",target_solar:"Solar target: {pct}",click_to_set:"Click to set position",target_tooltip:"Target {pct}%",target_tooltip_override:"Would-be solar target {pct}% — cover is held by manual override",tilt_title:"Tilt",tilt_target:"Tilt: {pct}",tilt_click_to_set:"Click to set tilt",tilt_target_tooltip:"Tilt target {pct}%"},decision:{placeholder:"Decision trace not yet populated.",pipeline:"Pipeline",winner:"Winner: {name}",summary_tooltip:"Why this position?",not_evaluated:"not evaluated",floor_suffix:" floor",outside_schedule:"Outside schedule — automatic control paused",outside_schedule_tooltip:"The configured schedule window is not active, so automatic positioning is paused.",solar_would_be:"solar {pct}",next_change_in:"Next adjustment allowed in {time}"},solar:{title:"Solar Calculation",axis_position:"Position axis",axis_tilt:"Tilt axis",group_inputs:"Inputs",group_intermediates:"Intermediates",group_output:"Output",show_all:"Show all {count} values",show_less:"Show less",no_target:"No solar target — {status}",status:{direct_sun:"Direct sun",fov_exit:"Default · FOV exit",elevation_limit:"Default · elevation limit",sunset_offset:"Default · sunset offset",blind_spot:"Default · blind spot",default:"Default"},field:{sol_elev_deg:"Sun elevation",gamma_deg:"Relative azimuth (γ)",position_pct:"Position",effective_distance_m:"Effective distance",adjusted_height_m:"Adjusted height",safety_margin:"Safety margin",awn_angle_deg:"Awning angle",vertical_position_m:"Vertical position",length_m:"Extension length",slat_angle_raw_deg:"Slat angle",tilt_mode:"Tilt mode",max_degrees:"Max angle"}},header:{on:"ON",off:"OFF",integration_enabled:"Integration Enabled",auto:"Auto",automatic_control:"Automatic Control"},tile:{battery:"Shade battery",motion_pending:"Motion timeout pending",motion_detected:"Motion detected",open:"Open",stop:"Stop",close:"Close",resume_aria:"Resume automatic control",registry_failed:"Registry fetch failed: {error}",loading:"Loading…",entry_not_found:"Adaptive Cover window {entry} not found."},formatters:{expired:"expired"},elevation:{title:"Sun today",fov_window:"FOV: {from} → {to}",fov_windows:"FOV: {windows}",fov_window_named:"{name}: {windows}",no_fov_today:"Sun does not enter FOV today",placeholder:"Sun elevation chart unavailable.",schedule:"Schedule {from} – {to}",schedule_from:"Schedule from {from}",schedule_until:"Schedule until {to}",schedule_start_tooltip:"Schedule start",schedule_end_tooltip:"Schedule end"},root:{loading_registry:"Loading Adaptive Cover registry…",no_entities_title:"No Adaptive Cover entities found",footer_version:"adaptive-cover-card v{version}",compass_no_match:"No matching Adaptive Cover entities",compass_configured:"Configured windows: {entries}",compass_not_found:"Windows not found: {entries}"},editor:{common:{window:"Window",title_optional:"Title (optional)",title_placeholder:"e.g. West-facing windows",north_offset:"Compass north offset (°)",north_offset_hint:'Rotate the compass clockwise so "up" matches your map. Default: 0.',loading_entries:"Loading Adaptive Cover windows…",load_failed:"Failed to load the windows: {error}",no_entries:"No Adaptive Cover windows found. Add a window under",no_entries_path:"Settings → Devices & Services",no_entries_then:", then come back.",window_manual_placeholder:"Enter the window key (window_key attribute)",window_fallback_label:"Window key",unknown_entry:"(unknown: {entry})",reset:"Reset"},main:{sections:"Sections",sections_hint:"Toggle which parts of the card are shown.",section_sky_label:"Sky compass",section_sky_desc:"Sun vs. window FOV, polar plot",section_elevation_label:"Sun today",section_elevation_desc:"Elevation-vs-time chart with FOV band and current-time cursor",section_decision_label:"Decision strip",section_decision_desc:"The engine decision trace with the winning step highlighted",section_covers_label:"Cover positions",section_covers_desc:"Per-cover live vs. target bars; click to set position",section_overrides_label:"Overrides panel",section_overrides_desc:"Manual override tile + reset button",section_climate_label:"Climate panel",section_climate_desc:"Summer/winter/intermediate strategy; shows standby when climate mode is off or inactive",controls:"Controls",controls_hint:"Render as read-only (visible but not clickable).",automatic_pill_label:"Automatic Control pill",automatic_pill_desc:"Allow toggling automatic control from the card header.",reset_button_label:"Reset Manual Override button",reset_button_desc:"Allow pressing the reset tile in the overrides panel.",display:"Display",compact_label:"Compact mode",compact_desc:"Tighter spacing between sections.",show_compass_stats_label:"Show compass stats",show_compass_stats_desc:"Azi, Elev, ∠, and Window angle below the sky compass.",show_compass_legend_label:"Show compass legend",show_compass_legend_desc:"Color key below the sky compass.",show_moon_label:"Show moon on compass",show_moon_desc:"Moon position and phase overlay on the sky compass.",hide_inactive_label:"Hide inactive handlers",hide_inactive_desc:"Show only the winner and actively matched pipeline handlers."},tile:{name:"Title override",icon:"Icon override",cover:"Cover entity",layout:"Layout",show_position:"Show position %",show_state:"Show state (Open/Closed)",show_decision_summary:"Show decision summary",show_controls:"Show ↑■▼ controls",show_badge:"Show contextual badge",badge_section:"Badges",badge_auto:"Auto",badge_solar:"Solar tracking",badge_manual:"Manual override",badge_climate:"Climate",badge_glare_zone:"No glare",badge_privacy:"Privacy",badge_sunset:"Sunset",show_compass:"Show sun compass in dialog",show_elevation_chart:"Show sun-today chart in dialog",tap_action:"Tap action",hold_action:"Hold action",double_tap_action:"Double-tap action",cover_blank_hint:"Leave blank to use the first managed cover automatically.",layout_option_one_line:"One line (compact)",layout_option_detailed:"Detailed (title, state, indicators)"},compass:{instances:"Windows",instances_hint:"Pick one or more. Each selected window adds an overlay to the compass.",cover_colors:"Cover colors",cover_colors_hint:"Override the default palette color for each overlay.",default_color:"default",display:"Display",toggle_compact_label:"Compact mode",toggle_compact_desc:"Smaller SVG, legend hidden.",toggle_legend_label:"Legend",toggle_legend_desc:"Color swatches + entry labels below compass.",toggle_stats_label:"Stats",toggle_stats_desc:"Sun + per-window numeric rows.",toggle_moon_label:"Moon",toggle_moon_desc:"Render moon position and phase.",toggle_cardinals_label:"Cardinal labels",toggle_cardinals_desc:"N/E/S/W letters around the compass.",toggle_blind_spot_label:"Blind spots",toggle_blind_spot_desc:"Hatched wedges for each window’s blind range.",toggle_sun_path_label:"Sun path",toggle_sun_path_desc:"Today’s sun arc across the sky.",toggle_sunrise_sunset_label:"Sunrise / sunset markers",toggle_sunrise_sunset_desc:"Small dots at rise and set azimuths.",toggle_cover_fill_label:"Cover closure fill",toggle_cover_fill_desc:"Inner wedge showing how closed each cover is.",toggle_window_arrow_label:"Window-normal arrow",toggle_window_arrow_desc:"Line from center toward each window’s azimuth.",toggle_elevation_chart_label:"Sun-today chart",toggle_elevation_chart_desc:"Elevation-vs-time chart below the compass, with FOV band and elevation limits."},decision:{title:"Title (optional)",compact_label:"Compact mode",compact_desc:"Tighter rows; also hides inactive handlers.",hide_inactive_handlers_label:"Hide inactive handlers",hide_inactive_handlers_desc:"Show only the winner and actively matched pipeline handlers.",show_decision_summary_label:"Show decision summary",show_decision_summary_desc:'Render a plain-English "Why this position?" sentence above the strip.'},house:{title:"Title",title_help:"Default: Shades.",floors:"Floors",floors_help:"Show only these floors. Leave empty for the whole house.",areas:"Rooms",areas_help:"Show only these rooms (added to the floors above).",layout:"Layout",layout_help:"Automatic uses the phone layout when the card is narrow.",layout_auto:"Automatic",layout_wide:"Wide",layout_narrow:"Phone",show_upcoming:'Show "Coming up"'}},house:{card_name:"Adaptive Cover house",card_description:"Every window by floor and room, with Auto / Hold / Off for the house, each room and each window.",title:"Shades",count:{window_one:"{n} window",window_other:"{n} windows",room_one:"{n} room",room_other:"{n} rooms",floor_one:"{n} floor",floor_other:"{n} floors"},sun_up:"Sun {azimuth}° · {elevation}° up · sets {time}",sun_up_short:"{elevation}° up · sets {time}",sun_down:"Sun down · rises {time}",sun_down_plain:"Sun down",whole_house:"Whole house",these_windows:"These windows",all_auto:"All on auto",all_hold:"All on hold",all_off:"All off",mixed_long:"Mixed: {auto} auto, {hold} hold, {off} off",mixed_short:"{auto} auto · {hold} hold · {off} off",return_all:"Return all to auto",open_all:"Open all",close_all:"Close all",climate:"Climate",climate_state:{summer:"Cooling",winter:"Heating",intermediate:"Mild",on:"On",off:"Off",mixed:"On for {on} of {total}"},settings:"House settings",settings_short:"Settings",mode:{auto:"Auto",hold:"Hold",off:"Off",mixed:"Mixed"},house_mode_label:"House mode",room_mode_label:"{room} mode",window_mode_label:"Window mode",hold_disabled:"Hold starts when a shade is moved by hand or with Open or Close. It ends after the manual-override time, or when you pick Auto.",filter:{label:"Filter windows",all:"All {n}",sun:"Sun on glass · {n}",hold:"On hold · {n}",off:"Off · {n}"},room_sun:"sun on {n}",room_mixed:"mixed",sun_on_glass:"Sun on the glass",chip_hold_left:"Hold · {left}",left_under_minute:"under 1m",next:{move:"Next: {position} at {time}",change:"Next change at {time}",none:"No change planned",hold:"Back to auto in {left}",hold_unknown:"On hold",off:"Automatic control is off",unavailable:"Unavailable"},why:{title:"Why this position",hold:"On hold until {time}. Auto takes over again after that.",hold_unknown:"On hold. Pick Auto to return it now.",off:"Automatic control is off for this window. It moves only when someone moves it.",none:"No decision recorded yet.",steps:"Show the steps"},sheet:{label:"Window details",close:"Close window details",open:"Open",stop:"Stop",close_cover:"Close",mode:"Mode",open_word:"open",target:"Target {position}",hold_hint:"To hold this shade, move it with Open or Close. Auto takes over again after the manual-override time.",hold_for:"Hold for",hold_1h:"1 h",hold_2h:"2 h",hold_4h:"4 h",hold_tonight:"Until tonight",setup:"Window setup",setup_hint:"Cover, direction, size. Set once.",faces:"Faces {deg}° {dir}"},upcoming:{title:"Coming up",today:"next 24 h",follows:"Moves to {position}",changes:"Changes position",sunset:"Sunset",sunset_detail:"Windows on auto go to their evening position"},empty:"No Adaptive Cover windows found. Add a window under Settings → Devices & services.",empty_filter:"No windows match this filter.",action_failed:"Adaptive Cover: {message}",strategy_name:"Adaptive Cover shades",strategy_description:"A dashboard with every Adaptive Cover window, by floor and room.",menu:"More for {name}",room_settings:"Room settings",floor_settings:"Floor settings"},settings:{sheet_label:"{name} settings",close:"Close settings",title:{house:"House settings",floor:"{name} floor",area:"{name}"},eyebrow:{house:"Whole house",floor:"Floor settings",area:"Room settings"},intro:{house:"Set once for the house. A floor or room overrides only what it needs.",floor:"Rooms on this floor use these, unless a room sets its own.",area:"This room uses the house settings, except what you set here."},more:"More house settings",more_hint:"Detection, outside sensors, privacy delay: on the house device.",level:{house:"house",floor:"floor",area:"room"},state:{own:"This {level}: {value}",own_unknown:"Set for this {level}",from_house:"From the house",from_floor:"From {floor}",unknown:"Set per window here"},house_value:"House: {value}",house_unknown:"House value not shown",house_per_floor:"Set per floor",save:"Save",save_here:"Set for this {level}",reset:"Reset to house",reset_floor:"Reset to {floor}",exceptions:"Set elsewhere",legacy_mark:"(kept from before)",legacy_setting:"{name} (kept from before)",window_exceptions:"Windows with their own values",window_exceptions_hint:"Change these in the window setup, under Exceptions.",section:{hand:"Hand moves",comfort:"Comfort",schedule:"Daily schedule",positions:"Positions",glare:"Glare",privacy:"Privacy"},value:{on:"On",off:"Off",none:"None",unset:"Not set",midnight:"Midnight",minutes:"{m} min",hours:"{h} h",hours_minutes:"{h} h {m} min",at_sunrise:"At sunrise",at_sunset:"At sunset",before_sunrise:"{n} min before sunrise",after_sunrise:"{n} min after sunrise",before_sunset:"{n} min before sunset",after_sunset:"{n} min after sunset"},label:{manual_override_duration:"A hand move holds a window for",manual_override_reset:"A later hand move restarts the hold",manual_detection:"Detect hand moves",manual_ignore_intermediate:"Ignore moves while opening or closing",manual_threshold:"Smallest hand move that counts",climate_on:"Climate",climate_mode:"Climate mode",temp_low:"Let sun in below",temp_high:"Block heat above",temp_entity:"Indoor temperature sensor",use_outside_temp:"Use outside temperature",use_lux:"Use the lux sensor",use_irradiance:"Use the irradiance sensor",start_time:"Start following the sun at",start_entity:"Start time from an entity",sunrise_offset:"Start following the sun",end_time:"Stop following the sun at",end_entity:"End time from an entity",sunset_offset:"Evening position from",return_sunset:"Go to the evening position at the end time",default_percentage:"Position when the sun is not on the glass",sunset_position:"Evening position",eye_height:"Eye height",occupied_distance:"Seat distance from the window",privacy_offset:"Privacy delay after sunset",privacy_position:"Privacy position",delta_position:"Smallest move",delta_time:"Time between moves",quiet_start:"Quiet hours start",quiet_end:"Quiet hours end",max_moves_hour:"Most moves per hour",weather_entity:"Weather",weather_state:"Weather counts as sunny when",presence_entity:"Presence",outside_temp:"Outside temperature sensor",outside_threshold:"Outside temperature threshold",lux_entity:"Lux sensor",lux_threshold:"Bright enough (lux)",irradiance_entity:"Irradiance sensor",irradiance_threshold:"Bright enough (W/m²)"},hint:{manual_override_duration:"Then it goes back to auto",climate_on:"Temperature, presence and weather steer the shades",climate_mode:"Climate inputs for these windows; a change reloads them",temp_low:"Indoor temperature: heating",temp_high:"Indoor temperature: cooling",sunrise_offset:"Minutes after sunrise (negative: before)",sunset_offset:"Minutes after sunset (negative: before)",default_percentage:"% open",sunset_position:"% open, after sunset",eye_height:"Where people sit, for glare",occupied_distance:"Where people sit, for glare",privacy_position:"% open, for street-facing windows"}}};function Ve(e,t){const o=function(e){let t=We;for(const o of e.split(".")){if("object"!=typeof t||null===t)return;t=t[o]}return"string"==typeof t?t:void 0}(e);return void 0===o?e:function(e,t){return t?e.replace(/\{(\w+)\}/g,(e,o)=>Object.prototype.hasOwnProperty.call(t,o)?String(t[o]):e):e}(o,t)}const Ge=e=>(...t)=>({_$litDirective$:e,values:t});class Ue{constructor(e){}get _$AU(){return this._$AM._$AU}_$AT(e,t,o){this._$Ct=e,this._$AM=t,this._$Ci=o}_$AS(e,t){return this.update(e,t)}update(e,t){return this.render(...t)}}const Le=(e,t)=>{const o=e._$AN;if(void 0===o)return!1;for(const e of o)e._$AO?.(t,!1),Le(e,t);return!0},Ye=e=>{let t,o;do{if(void 0===(t=e._$AM))break;o=t._$AN,o.delete(e),e=t}while(0===o?.size)},He=e=>{for(let t;t=e._$AM;e=t){let o=t._$AN;if(void 0===o)t._$AN=o=new Set;else if(o.has(e))break;o.add(e),Xe(t)}};function Qe(e){void 0!==this._$AN?(Ye(this),this._$AM=e,He(this)):this._$AM=e}function qe(e,t=!1,o=0){const i=this._$AH,s=this._$AN;if(void 0!==s&&0!==s.size)if(t)if(Array.isArray(i))for(let e=o;e<i.length;e++)Le(i[e],!1),Ye(i[e]);else null!=i&&(Le(i,!1),Ye(i));else Le(this,e)}const Xe=e=>{2==e.type&&(e._$AP??=qe,e._$AQ??=Qe)};class Je extends Ue{constructor(){super(...arguments),this._$AN=void 0}_$AT(e,t,o){super._$AT(e,t,o),He(this),this.isConnected=e._$AU}_$AO(e,t=!0){e!==this.isConnected&&(this.isConnected=e,e?this.reconnected?.():this.disconnected?.()),t&&(Le(this,e),Ye(this))}setValue(e){if((()=>void 0===this._$Ct.strings)())this._$Ct._$AI(e,this);else{const t=[...this._$Ct._$AH];t[this._$Ci]=e,this._$Ct._$AI(t,this,0)}}disconnected(){}reconnected(){}}const Ze=[12,16];function et(e,t,o=0){const i=(e-90+o)*Math.PI/180;return{x:t*Math.cos(i),y:t*Math.sin(i)}}function tt(e){return 1-Math.max(0,Math.min(90,e))/90}function ot(e,t,o,i=0,s=0){const n=e=>(e%360+360)%360,r=n(e),a=n(t);let l=a-r;l<0&&(l+=360);const c=l>180?1:0,d=et(r,o,s),h=et(a,o,s);if(i<=0)return`M 0 0 L ${d.x} ${d.y} A ${o} ${o} 0 ${c} 1 ${h.x} ${h.y} Z`;const u=et(a,i,s),p=et(r,i,s);return[`M ${d.x} ${d.y}`,`A ${o} ${o} 0 ${c} 1 ${h.x} ${h.y}`,`L ${u.x} ${u.y}`,`A ${i} ${i} 0 ${c} 0 ${p.x} ${p.y}`,"Z"].join(" ")}function it(e,t,o=0){return et(e,tt(t),o)}function st(e){return(e%360+360)%360}function nt(e,t,o,i){const s=i??0;let n=-1,r=-1;for(let i=t;i<=o&&i<e.length;i++)e[i].elevation>s&&(-1===n&&(n=i),r=i);return-1===n?null:{wedgeStart:e[n].azimuth,wedgeEnd:e[r].azimuth}}function rt(e,t,o){const i=(e-t)/864e5;return Math.max(0,Math.min(o,i*o))}function at(e,t,o){return((e-t)%360+360)%360<=((o-t)%360+360)%360}function lt(e,t,o,i){return at(o,e,t)||at(i,e,t)||at(e,o,i)||at(t,o,i)}function ct(e,t,o,i){const s="cover_awning"===t?e/100:1-e/100;return Math.min(o*s,i)}function dt(e,t){return e<.5?-4*t*e:4*t*(1-e)}function ht(e,t,o,i,s){const n=et(o,1),r=-n.y,a=n.x,l=e-n.x*i,c=t-n.y*i;return`M ${e} ${t} L ${l+r*s} ${c+a*s} L ${l-r*s} ${c-a*s} Z`}let ut=class extends ce{constructor(){super(...arguments),this.text="",this.cursorX=0,this.cursorY=0,this.offset=Ze,this.visible=!1,this._x=0,this._y=0}connectedCallback(){super.connectedCallback(),this.hasAttribute("role")||this.setAttribute("role","tooltip")}updated(){if(!this.visible)return;this.setAttribute("aria-hidden","false");const e=this.shadowRoot?.querySelector(".bubble"),t=e?.offsetWidth??0,o=e?.offsetHeight??0,i="undefined"!=typeof window?window.innerWidth:0,s="undefined"!=typeof window?window.innerHeight:0,{x:n,y:r}=function(e){const{cursorX:t,cursorY:o,ttW:i,ttH:s,vpW:n,vpH:r}=e,[a,l]=e.offset??Ze;let c=t+a,d=!1;c+i>n&&(c=t-a-i,d=!0),c<0&&(c=0);let h=o+l;return h+s>r&&(h=o-l-s),h<0&&(h=0),{x:c,y:h,flipped:d}}({cursorX:this.cursorX,cursorY:this.cursorY,ttW:t,ttH:o,vpW:i,vpH:s,offset:this.offset});n!==this._x&&(this._x=n),r!==this._y&&(this._y=r)}render(){return this.visible?G`<div class="bubble" style="transform: translate3d(${this._x}px, ${this._y}px, 0)">
      ${this.text}
    </div>`:(this.setAttribute("aria-hidden","true"),Y)}};ut.styles=r`
    :host {
      position: fixed;
      top: 0;
      left: 0;
      z-index: 100000;
      pointer-events: none;
    }
    :host(:not([visible])) {
      display: none;
    }
    .bubble {
      position: absolute;
      top: 0;
      left: 0;
      width: max-content;
      max-width: 280px;
      padding: 6px 10px;
      border-radius: 6px;
      background: var(--acp-tooltip-bg, rgba(40, 40, 40, 0.96));
      color: var(--acp-tooltip-fg, #fff);
      font-size: 0.78rem;
      line-height: 1.35;
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
      white-space: normal;
      word-break: break-word;
    }
  `,e([ge({type:String})],ut.prototype,"text",void 0),e([ge({type:Number})],ut.prototype,"cursorX",void 0),e([ge({type:Number})],ut.prototype,"cursorY",void 0),e([ge({attribute:!1})],ut.prototype,"offset",void 0),e([ge({type:Boolean,reflect:!0})],ut.prototype,"visible",void 0),e([me()],ut.prototype,"_x",void 0),e([me()],ut.prototype,"_y",void 0),ut=e([he("acp-floating-tooltip")],ut);const pt={enabled:!0,offset:Ze,delay:400};function gt(e){void 0!==e.enabled&&(pt.enabled=e.enabled),void 0!==e.offset&&(pt.offset=e.offset),void 0!==e.delay&&(pt.delay=e.delay)}const mt="acp-floating-tooltip-bubble",ft=new class{constructor(){this._el=null,this._refs=0}get id(){return mt}retain(){this._refs+=1,this._ensure()}release(){this._refs=Math.max(0,this._refs-1)}_ensure(){if("undefined"==typeof document)return null;if(this._el&&this._el.isConnected)return this._el;const e=document.createElement("acp-floating-tooltip");return e.id=mt,document.body.appendChild(e),this._el=e,e}show(e,t,o,i){const s=this._ensure();s&&(s.text=e,s.cursorX=t,s.cursorY=o,s.offset=i,s.visible=!0)}move(e,t){this._el&&this._el.visible&&(this._el.cursorX=e,this._el.cursorY=t)}hide(){this._el&&(this._el.visible=!1)}_reset(){this._el&&this._el.parentNode&&this._el.parentNode.removeChild(this._el),this._el=null,this._refs=0}},_t=Ge(class extends Je{constructor(e){if(super(e),this._el=null,this._text="",this._offset=Ze,this._delay=400,this._enabled=!0,this._openTimer=null,this._shown=!1,this._retained=!1,this._lastX=0,this._lastY=0,this._onEnter=e=>this._handleEnter(e),this._onMove=e=>this._handleMove(e),this._onLeave=()=>this._dismiss(),this._onFocus=()=>this._handleFocus(),this._onBlur=()=>this._dismiss(),this._onKey=e=>{"Escape"===e.key&&this._dismiss()},this._onScroll=()=>this._dismiss(),6!==e.type)throw new Error("tooltip() can only be used as an element-part directive")}render(e,t){return Y}update(e,[t,o]){const i=e.element;return this._text=t??"",this._offset=o?.offset??pt.offset,this._delay=o?.delay??pt.delay,this._enabled=o?.enabled??pt.enabled,this._el!==i?(this._teardown(),this._el=i,this._wire()):this._applyAttributes(),this.render(t,o)}_wire(){const e=this._el;e&&(this._applyAttributes(),this._enabled&&(ft.retain(),this._retained=!0,e.addEventListener("pointerenter",this._onEnter),e.addEventListener("pointermove",this._onMove),e.addEventListener("pointerleave",this._onLeave),e.addEventListener("focusin",this._onFocus),e.addEventListener("focusout",this._onBlur),e.addEventListener("keydown",this._onKey),window.addEventListener("scroll",this._onScroll,!0)))}_applyAttributes(){const e=this._el;e&&(this._enabled?(e.removeAttribute("title"),e.setAttribute("data-tooltip",this._text),e.setAttribute("aria-describedby",ft.id)):(e.removeAttribute("data-tooltip"),e.removeAttribute("aria-describedby"),e.removeAttribute("acp-tt-shown"),e.setAttribute("title",this._text)))}_handleEnter(e){this._lastX=e.clientX,this._lastY=e.clientY,this._armOpen()}_handleFocus(){const e=this._el;if(e&&"function"==typeof e.getBoundingClientRect){const t=e.getBoundingClientRect();this._lastX=t.left+t.width/2,this._lastY=t.bottom}this._armOpen()}_armOpen(){null===this._openTimer&&(this._openTimer=setTimeout(()=>{this._openTimer=null,this._open()},this._delay))}_open(){this._el&&(ft.show(this._text,this._lastX,this._lastY,this._offset),this._shown=!0,this._el.setAttribute("acp-tt-shown",""))}_handleMove(e){this._lastX=e.clientX,this._lastY=e.clientY,this._shown&&ft.move(this._lastX,this._lastY)}_dismiss(){null!==this._openTimer&&(clearTimeout(this._openTimer),this._openTimer=null),this._shown&&(ft.hide(),this._shown=!1),this._el?.removeAttribute("acp-tt-shown")}_teardown(){const e=this._el;e&&(this._dismiss(),e.removeEventListener("pointerenter",this._onEnter),e.removeEventListener("pointermove",this._onMove),e.removeEventListener("pointerleave",this._onLeave),e.removeEventListener("focusin",this._onFocus),e.removeEventListener("focusout",this._onBlur),e.removeEventListener("keydown",this._onKey),"undefined"!=typeof window&&window.removeEventListener("scroll",this._onScroll,!0),this._retained&&(ft.release(),this._retained=!1),this._el=null)}disconnected(){this._teardown()}reconnected(){this._wire()}});function vt(e){return"string"==typeof e&&e.length>0}function yt(e){return e?vt(e.window)?{kind:"window",key:e.window}:vt(e.entry_id)?{kind:"entry",key:e.entry_id}:vt(e.cover)?{kind:"cover",entity_id:e.cover}:null:null}function wt(e){if(!e)return[];const t=[];for(const o of e.windows??[])vt(o)&&t.push({kind:"window",key:o});for(const o of e.covers??[])vt(o)&&t.push({kind:"cover",entity_id:o});for(const o of e.entry_ids??[])vt(o)&&t.push({kind:"entry",key:o});return t}function bt(e){return"cover"===e.kind?`cover:${e.entity_id}`:e.key}function xt(e){return"cover"===e.kind?e.entity_id:e.key}function $t(e,t){const o={...e,window:t};return delete o.entry_id,o}function kt(e){return e?vt(e.window)?e.window:vt(e.entry_id)?e.entry_id:"":""}const St=(()=>{const e={};for(const[t,o]of Object.entries(Be)){const i=t.indexOf(":"),s=t.slice(0,i);(e[s]??(e[s]=[])).push({suffix:t.slice(i+1),role:o})}for(const t of Object.values(e))t.sort((e,t)=>t.suffix.length-e.suffix.length);return e})(),At=new Set(["cover_blind","cover_awning","cover_tilt"]),Ct=new WeakMap;function Et(e){if(e.platform!==Me||"string"!=typeof e.unique_id)return null;const t=e.entity_id.split(".")[0];for(const{suffix:o,role:i}of St[t]??[]){const t=`_${o}`;if(e.unique_id.length>t.length&&e.unique_id.endsWith(t))return{key:e.unique_id.slice(0,-t.length),role:i}}return null}function Mt(e){const t=Ct.get(e);if(t)return t;const o=new Map;for(const t of e){const e=Et(t);if(!e)continue;let i=o.get(e.key);i||(i={key:e.key,entities:{}},o.set(e.key,i)),i.entities[e.role]||(i.entities[e.role]=t.entity_id),"target_position_sensor"!==e.role||i.position||(i.position=t,t.device_id&&(i.deviceId=t.device_id)),!i.deviceId&&t.device_id&&(i.deviceId=t.device_id)}const i={byKey:o,withPosition:[...o.values()].filter(e=>e.position)};return Ct.set(e,i),i}function zt(e,t){const o=t.position?.entity_id;return o?e.states[o]?.attributes:void 0}function Ot(e){return"string"==typeof e&&e.length>0}function It(e){const t=Ot(e?.cover_entity)?e.cover_entity:null,o=Array.isArray(e?.cover_entities)?e.cover_entities.filter(Ot):[],i=t?[t,...o]:o;return[...new Set(i)]}function Tt(e){return[...new Set([...Object.keys(e?.last_moves??{}),...Object.keys(e?.move_blocked_by??{})])].sort()}function Ft(e,t){const o=zt(e,t)?.window_key;return{rows:t,windowKey:Ot(o)?o:t.key}}function Rt(e,t,o){if("cover"===t.kind){const i=t.entity_id;for(const t of o.withPosition)if(zt(e,t)?.cover_entity===i)return Ft(e,t);for(const t of o.withPosition)if(It(zt(e,t)).includes(i))return Ft(e,t);for(const t of o.withPosition){const o=zt(e,t);if(!(It(o).length>0)&&Tt(o).includes(i))return Ft(e,t)}return null}for(const i of o.withPosition)if(zt(e,i)?.window_key===t.key)return{rows:i,windowKey:t.key};const i=o.byKey.get(t.key);return i?{rows:i,windowKey:t.key}:null}function jt(e,t){const o=e.devices;if(o){const e=t.rows.deviceId?o[t.rows.deviceId]:void 0;if(e)return e.name_by_user||e.name||t.windowKey;if(!t.rows.deviceId)for(const e of Object.values(o))if(e.config_entries?.includes(t.windowKey))return e.name_by_user||e.name||t.windowKey}return t.windowKey}function Nt(e,t){const o=zt(e,t.rows),i=It(o),s=i.length>0?i:Tt(o);let n="cover_blind";if(Ot(o?.cover_type)&&At.has(o.cover_type))n=o.cover_type;else if(s.length>0){const t=s.every(t=>{const o=e.states[t]?.attributes;return void 0!==o?.current_tilt_position&&void 0===o?.current_position});t&&(n="cover_tilt")}return{window_key:t.windowKey,entry_id:t.windowKey,entry_title:jt(e,t),cover_type:n,entities:{...t.rows.entities},managed_covers:s,device_id:t.rows.deviceId,config_entry_id:t.rows.position?.config_entry_id??null,config_subentry_id:t.rows.position?.config_subentry_id??null}}function Pt(e){return e?"kind"in e&&"string"==typeof e.kind?e:yt(e):null}function Dt(e,t,o){const i=Pt(t);if(!i)return null;const s=Rt(e,i,Mt(o));return s?Nt(e,s):null}function Kt(e,t,o){const i=Pt(t);if(!i)return[];const s=Rt(e,i,Mt(o));if(!s)return[];const n=`${s.rows.key}_`;return o.filter(e=>e.platform===Me&&e.unique_id?.startsWith(n))}function Bt(){let e=null;return(t,o,i)=>{const s=Pt(o),n=s?Rt(t,s,Mt(i)):null;if(!n)return e=null,null;const r=t.devices,a=n.rows.entities.target_position_sensor,l=n.rows.entities.control_status_sensor,c=a?t.states[a]:void 0,d=l?t.states[l]:void 0;if(null!==e&&e.registry===i&&e.rows===n.rows&&e.windowKey===n.windowKey&&e.devices===r&&e.posState===c&&e.ctrlState===d)return e.result;const h=Nt(t,n);return e={registry:i,rows:n.rows,windowKey:n.windowKey,devices:r,posState:c,ctrlState:d,result:h},h}}async function Wt(e){return e.callWS({type:"config/entity_registry/list"})}function Vt(e,t){let o=null,i=!1;return e.connection.subscribeEvents(e=>t(e.data),"entity_registry_updated").then(e=>{i?e():o=e}).catch(()=>{}),()=>{i=!0,o&&o()}}let Gt=null,Ut=null;function Lt(){return Gt}function Yt(e,t=!1){if(Ut)return Ut;if(!t&&Gt)return Promise.resolve(Gt);const o=Wt(e).then(e=>(Gt=e,Ut=null,e)).catch(e=>{throw Ut=null,e});return Ut=o,o}async function Ht(e){try{const t=await e.callWS({type:"config_entries/get",domain:Me}),o={};for(const e of Array.isArray(t)?t:[])e?.domain===Me&&e.entry_id&&e.title&&(o[e.entry_id]=e.title);return o}catch{return{}}}async function Qt(e){const[t,o]=await Promise.all([Yt(e),Ht(e)]);return function(e,t,o={}){const i=[];for(const s of Mt(t).withPosition){if(s.position?.disabled_by)continue;const t=Ft(e,s);let n=jt(e,t);n===t.windowKey&&o[t.windowKey]&&(n=o[t.windowKey]);const r={window_key:t.windowKey,title:n},a=It(zt(e,s))[0];a&&(r.cover=a),i.push(r)}return i.sort((e,t)=>e.title.localeCompare(t.title)||e.window_key.localeCompare(t.window_key))}(e,Array.isArray(t)?t:[],o)}function qt(e){return`acp-card:registry:v1:${e}`}const Xt={get(e){try{const t=localStorage.getItem(qt(e));if(!t)return null;const o=JSON.parse(t);return 1!==o.schemaVersion?null:o.entries?.length?"number"==typeof o.fetchedAt&&Date.now()-o.fetchedAt>6e4?null:o:null}catch{return null}},set(e,t){if(0!==t.length)try{const o={schemaVersion:1,cardVersion:_e,fetchedAt:Date.now(),entries:t};localStorage.setItem(qt(e),JSON.stringify(o))}catch{}},invalidate(e){try{localStorage.removeItem(qt(e))}catch{}},clear(){try{const e="acp-card:registry:v1:",t=[];for(let o=0;o<localStorage.length;o++){const i=localStorage.key(o);i?.startsWith(e)&&t.push(i)}t.forEach(e=>localStorage.removeItem(e))}catch{}}};function Jt(e){return`${e.entity_id}|${e.unique_id}|${e.platform}|${e.config_entry_id??""}`}let Zt=class extends ce{constructor(){super(...arguments),this.on=!1,this.readonly=!1,this.label="",this.title=""}_handleClick(){this.readonly||this.dispatchEvent(new CustomEvent("pill-click",{bubbles:!0,composed:!0}))}render(){return G`
      <button
        class="pill ${this.on?"on":"off"} ${this.readonly?"readonly":""}"
        ${_t(this.title)}
        aria-disabled=${this.readonly?"true":Y}
        tabindex=${this.readonly?"-1":"0"}
        @click=${this._handleClick}
      >
        ${this.label}
      </button>
    `}};Zt.styles=r`
    .pill {
      padding: 2px 10px;
      border-radius: 999px;
      border: 1px solid var(--divider-color);
      background: transparent;
      font-size: 0.78rem;
      letter-spacing: 0.04em;
      cursor: pointer;
      color: var(--secondary-text-color);
    }
    .pill.on {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
      border-color: transparent;
    }
    .pill.off {
      opacity: 0.6;
    }
    .pill.readonly {
      cursor: default;
      opacity: 0.85;
    }
    /* Readonly pills aren't clickable, so a help cursor is a useful "hover for
       more" hint; clickable pills keep their pointer cursor (below). The shown
       state reverts to default once OUR bubble appears. */
    .pill.readonly[data-tooltip]:hover {
      cursor: help;
    }
    .pill[data-tooltip][acp-tt-shown] {
      cursor: default;
    }
    .pill.on.readonly {
      opacity: 0.85;
    }
  `,e([ge({type:Boolean})],Zt.prototype,"on",void 0),e([ge({type:Boolean})],Zt.prototype,"readonly",void 0),e([ge({type:String})],Zt.prototype,"label",void 0),e([ge({type:String})],Zt.prototype,"title",void 0),Zt=e([he("acp-header-pill")],Zt);const eo=Ge(class extends Ue{constructor(e){if(super(e),1!==e.type||"class"!==e.name||e.strings?.length>2)throw Error("`classMap()` can only be used in the `class` attribute and must be the only part in the attribute.")}render(e){return" "+Object.keys(e).filter(t=>e[t]).join(" ")+" "}update(e,[t]){if(void 0===this.st){this.st=new Set,void 0!==e.strings&&(this.nt=new Set(e.strings.join(" ").split(/\s/).filter(e=>""!==e)));for(const e in t)t[e]&&!this.nt?.has(e)&&this.st.add(e);return this.render(t)}const o=e.element.classList;for(const e of this.st)e in t||(o.remove(e),this.st.delete(e));for(const e in t){const i=!!t[e];i===this.st.has(e)||this.nt?.has(e)||(i?(o.add(e),this.st.add(e)):(o.remove(e),this.st.delete(e)))}return L}});function to(e,t){const o=t.entities.target_position_sensor;if(!o)return;const i=e.states[o];return i?i.attributes:void 0}function oo(e,t){const o=to(e,t);return o?.intent??"default"}function io(e,t){const o=to(e,t);if(!o)return;const i=Array.isArray(o.decision_trace)?o.decision_trace:[],s=i.map((e,t)=>({handler:e,matched:t===i.length-1,reason:e,position:null}));return{trace:s,reason:i.length>0?i[i.length-1]:"",winner:o.intent??"default",sun_azimuth:o.sun?.azimuth,sun_elevation:o.sun?.elevation,gamma:o.sun?.gamma,in_field_of_view:o.sun?.in_fov,default_position:o.default,sunset_position:o.sunset_default}}function so(e,t){const o=to(e,t),i=o?.sun;return i&&"number"==typeof i.azimuth&&"number"==typeof i.elevation?i:null}function no(e,t,o){const i=e.states[o]?.attributes,s="cover_tilt"===t?i?.current_tilt_position:i?.current_position;return"number"==typeof s&&Number.isFinite(s)?s:null}function ro(e,t){const o=t.entities.target_position_sensor;if(!o)return null;const i=parseFloat(e.states[o]?.state??"");return Number.isNaN(i)?null:i}function ao(e,t){const o={};for(const i of t.managed_covers)o[i]=no(e,t.cover_type,i);return o}function lo(e,t){return 0===t.managed_covers.length?null:function(e){const t=Object.values(e).filter(e=>"number"==typeof e);return 0===t.length?null:t.reduce((e,t)=>e+t,0)/t.length}(ao(e,t))}function co(e,t){return ro(e,t)}function ho(e){return e&&e.__esModule&&Object.prototype.hasOwnProperty.call(e,"default")?e.default:e}var uo,po,go={exports:{}},mo=(uo||(uo=1,po=go,function(){var e=Math.PI,t=Math.sin,o=Math.cos,i=Math.tan,s=Math.asin,n=Math.atan2,r=Math.acos,a=e/180,l=864e5,c=2440588,d=2451545;function h(e){return new Date((e+.5-c)*l)}function u(e){return function(e){return e.valueOf()/l-.5+c}(e)-d}var p=23.4397*a;function g(e,s){return n(t(e)*o(p)-i(s)*t(p),o(e))}function m(e,i){return s(t(i)*o(p)+o(i)*t(p)*t(e))}function f(e,s,r){return n(t(e),o(e)*t(s)-i(r)*o(s))}function _(e,i,n){return s(t(i)*t(n)+o(i)*o(n)*o(e))}function v(e,t){return a*(280.16+360.9856235*e)-t}function y(e){return a*(357.5291+.98560028*e)}function w(o){return o+a*(1.9148*t(o)+.02*t(2*o)+3e-4*t(3*o))+102.9372*a+e}function b(e){var t=w(y(e));return{dec:m(t,0),ra:g(t,0)}}var x={getPosition:function(e,t,o){var i=a*-o,s=a*t,n=u(e),r=b(n),l=v(n,i)-r.ra;return{azimuth:f(l,s,r.dec),altitude:_(l,s,r.dec)}}},$=x.times=[[-.833,"sunrise","sunset"],[-.3,"sunriseEnd","sunsetStart"],[-6,"dawn","dusk"],[-12,"nauticalDawn","nauticalDusk"],[-18,"nightEnd","night"],[6,"goldenHourEnd","goldenHour"]];x.addTime=function(e,t,o){$.push([e,t,o])};var k=9e-4;function S(t,o,i){return k+(t+o)/(2*e)+i}function A(e,o,i){return d+e+.0053*t(o)-.0069*t(2*i)}function C(e,i,s,n,a,l,c){var d=function(e,i,s){return r((t(e)-t(i)*t(s))/(o(i)*o(s)))}(e,s,n);return A(S(d,i,a),l,c)}function E(e){var i=a*(134.963+13.064993*e),s=a*(93.272+13.22935*e),n=a*(218.316+13.176396*e)+6.289*a*t(i),r=5.128*a*t(s),l=385001-20905*o(i);return{ra:g(n,r),dec:m(n,r),dist:l}}function M(e,t){return new Date(e.valueOf()+t*l/24)}x.getTimes=function(t,o,i,s){var n,r,l,c,d,p=a*-i,g=a*o,f=function(e){return-2.076*Math.sqrt(e)/60}(s=s||0),_=function(t,o){return Math.round(t-k-o/(2*e))}(u(t),p),v=S(0,p,_),b=y(v),x=w(b),E=m(x,0),M=A(v,b,x),z={solarNoon:h(M),nadir:h(M-.5)};for(n=0,r=$.length;n<r;n+=1)d=M-((c=C(((l=$[n])[0]+f)*a,p,g,E,_,b,x))-M),z[l[1]]=h(d),z[l[2]]=h(c);return z},x.getMoonPosition=function(e,s,r){var l=a*-r,c=a*s,d=u(e),h=E(d),p=v(d,l)-h.ra,g=_(p,c,h.dec),m=n(t(p),i(c)*o(h.dec)-t(h.dec)*o(p));return g+=function(e){return e<0&&(e=0),2967e-7/Math.tan(e+.00312536/(e+.08901179))}(g),{azimuth:f(p,c,h.dec),altitude:g,distance:h.dist,parallacticAngle:m}},x.getMoonIllumination=function(e){var i=u(e||new Date),s=b(i),a=E(i),l=149598e3,c=r(t(s.dec)*t(a.dec)+o(s.dec)*o(a.dec)*o(s.ra-a.ra)),d=n(l*t(c),a.dist-l*o(c)),h=n(o(s.dec)*t(s.ra-a.ra),t(s.dec)*o(a.dec)-o(s.dec)*t(a.dec)*o(s.ra-a.ra));return{fraction:(1+o(d))/2,phase:.5+.5*d*(h<0?-1:1)/Math.PI,angle:h}},x.getMoonTimes=function(e,t,o,i){var s=new Date(e);i?s.setUTCHours(0,0,0,0):s.setHours(0,0,0,0);for(var n,r,l,c,d,h,u,p,g,m,f,_,v,y=.133*a,w=x.getMoonPosition(s,t,o).altitude-y,b=1;b<=24&&(n=x.getMoonPosition(M(s,b),t,o).altitude-y,p=((d=(w+(r=x.getMoonPosition(M(s,b+1),t,o).altitude-y))/2-n)*(u=-(h=(r-w)/2)/(2*d))+h)*u+n,m=0,(g=h*h-4*d*n)>=0&&(f=u-(v=Math.sqrt(g)/(2*Math.abs(d))),_=u+v,Math.abs(f)<=1&&m++,Math.abs(_)<=1&&m++,f<-1&&(f=_)),1===m?w<0?l=b+f:c=b+f:2===m&&(l=b+(p<0?_:f),c=b+(p<0?f:_)),!l||!c);b+=2)w=r;var $={};return l&&($.rise=M(s,l)),c&&($.set=M(s,c)),l||c||($[p>0?"alwaysUp":"alwaysDown"]=!0),$},po.exports=x}()),go.exports),fo=ho(mo);const _o=new Map;function vo(e,t,o,i=10){const s=`${e},${t},${o.getTime()},${i}`,n=_o.get(s);if(n)return _o.delete(s),_o.set(s,n),n;const r=[],a=o.getTime()+864e5;for(let s=o.getTime();s<=a;s+=60*i*1e3){const o=new Date(s),i=fo.getPosition(o,e,t);r.push({t:o,elevation:180*i.altitude/Math.PI,azimuth:((180*i.azimuth/Math.PI+180)%360+360)%360})}if(_o.set(s,r),_o.size>4){const e=_o.keys().next().value;void 0!==e&&_o.delete(e)}return r}function yo(e=new Date){const t=new Date(e);return t.setHours(0,0,0,0),t}function wo(e,t=new Date){if(!e)return yo(t);const o=new Intl.DateTimeFormat("en-CA",{timeZone:e,year:"numeric",month:"2-digit",day:"2-digit"}).format(t),[i,s,n]=o.split("-").map(Number),r=Date.UTC(i,s-1,n,0,0,0),a=function(e,t){const o=new Intl.DateTimeFormat("en-US",{timeZone:e,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit",hourCycle:"h23"}).formatToParts(t),i={};for(const e of o)"literal"!==e.type&&(i[e.type]=Number(e.value));return Date.UTC(i.year,i.month-1,i.day,i.hour,i.minute,i.second)-t.getTime()}(e,new Date(r));return new Date(r-a)}function bo(e,t,o,i){const s=((t-o)%360+360)%360;return((e-s)%360+360)%360<=((((t+i)%360+360)%360-s)%360+360)%360}function xo(e,t,o,i){const s=[];let n=-1;for(let r=0;r<e.length;r++){const a=e[r];a.elevation>0&&bo(a.azimuth,t,o,i)?-1===n&&(n=r):-1!==n&&(s.push({startIdx:n,endIdx:r-1}),n=-1)}return-1!==n&&s.push({startIdx:n,endIdx:e.length-1}),s}function $o(e,t,o=new Date){const i=fo.getMoonPosition(o,e,t),s=fo.getMoonIllumination(o);return{azimuth:((180*i.azimuth/Math.PI+180)%360+360)%360,elevation:180*i.altitude/Math.PI,phase:s.phase,fraction:s.fraction,phaseName:ko(s.phase)}}function ko(e){return e<.0625||e>=.9375?"New Moon":e<.1875?"Waxing Crescent":e<.3125?"First Quarter":e<.4375?"Waxing Gibbous":e<.5625?"Full Moon":e<.6875?"Waning Gibbous":e<.8125?"Last Quarter":"Waning Crescent"}function So(e){return null==e||Number.isNaN(e)?"—":`${Math.round(e)}%`}function Ao(e){return null==e||Number.isNaN(e)?"—":`${e.toFixed(1)}°`}function Co(e,t){if(!e)return"—";const o=new Date(e);return Number.isNaN(o.getTime())?"—":o.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",timeZone:t})}const Eo=new Set(["outside_fov","in_fov_not_valid","hitting"]),Mo={night:"sun night",hitting:"sun valid",in_fov_not_valid:"sun in-fov",outside_fov:"sun up"};function zo(e){return e.belowHorizon?"night":e.sunState&&Eo.has(e.sunState)?e.sunState:e.directSunValid?"hitting":e.inFov?"in_fov_not_valid":"outside_fov"}const Oo=["#1f77b4","#ff7f0e","#2ca02c","#d62728","#9467bd","#17becf","#e377c2"];function Io(e){const t=Oo.length;return Oo[(e%t+t)%t]}function To(e,t){return"string"==typeof e&&e.length>0?{color:e,isOverride:!0}:{color:Io(t),isOverride:!1}}const Fo="data:image/png;base64,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",Ro=110;let jo=0,No=class extends ce{constructor(){super(...arguments),this.discovered_list=[],this.compact=!1,this.showStats=!0,this.showLegend=!0,this.showMoon=!1,this.showCardinals=!0,this.showBlindSpot=!0,this.showSunPath=!0,this.showSunriseSunset=!0,this.showCoverFill=!0,this.showWindowArrow=!0,this.coverColors=[],this.northOffsetDeg=0,this._hiddenEntries=new Set,this._legendMoonMaskId="acp-legend-moon-"+jo++}shouldUpdate(e){return e.size>1||!e.has("hass")||fe(e.get("hass"),this.hass,this._relevantIds())}_relevantIds(){const e=[];for(const t of this.discovered_list){const o=t.entities;e.push(o.target_position_sensor,o.manual_override_binary,o.sun_infront_binary,o.start_sensor,o.end_sensor,...t.managed_covers)}return e}_toggleEntry(e){const t=new Set(this._hiddenEntries);t.has(e)?t.delete(e):t.add(e),this._hiddenEntries=t}_sunFor(e){return so(this.hass,e)}_sunInfrontFor(e){const t=e.entities.sun_infront_binary;return!!t&&"on"===this.hass.states[t]?.state}_sunDotStateFor(e,t){return zo({belowHorizon:t.elevation<=0,sunState:null,directSunValid:this._sunInfrontFor(e),inFov:!0===t.in_fov})}_readActiveAzimuth(e){if(!e)return null;const t=this.hass.states[e];if(!t)return null;if("unavailable"===t.state||"unknown"===t.state)return null;const o=t.attributes.azimuth;return"number"==typeof o&&Number.isFinite(o)?o:null}_buildOverlays(){const e=[];return this.discovered_list.forEach((t,o)=>{const i=this._sunFor(t);if(!i)return;const s=i.azimuth,{color:n,isOverride:r}=To(this.coverColors?.[o],o);e.push({d:t,sun:i,sunAzi:s,sunInfront:this._sunInfrontFor(t),dotState:this._sunDotStateFor(t,i),coverPos:co(this.hass,t),actualPos:lo(this.hass,t),coverType:t.cover_type,color:n,isOverride:r,index:o})}),e}render(){if(!this.hass)return Y;if(!this.discovered_list||0===this.discovered_list.length)return G`<div class="placeholder">${Ve("compass.placeholder_no_entries")}</div>`;const e=this._buildOverlays();if(0===e.length)return G`<div class="placeholder">${Ve("compass.placeholder_no_sun")}</div>`;const t=e.filter(e=>!this._hiddenEntries.has(e.d.window_key)),o=st(this.northOffsetDeg),i=e.length>1,s=e[0],n=s.sunAzi,r=s.sun.elevation,a=it(n,r,o),l={night:-1,outside_fov:0,in_fov_not_valid:1,hitting:2},c=r<=0?"night":e.reduce((e,t)=>l[t.dotState]>l[e]?t.dotState:e,"outside_fov"),d=Mo[c],{latitude:h,longitude:u,time_zone:p}=this.hass.config,g=void 0!==h&&void 0!==u?vo(h,u,wo(p)):[],m=this.showMoon&&void 0!==h&&void 0!==u?$o(h,u):null,f=null!==m&&m.elevation>0,_=m?dt(m.phase,6):0,v=f?it(m.azimuth,m.elevation,o):null,y=v?v.x*Ro:0,w=v?v.y*Ro:0,b=this.showSunPath?function(e){const t=[];let o=-1;for(let i=0;i<e.length;i++)e[i].elevation>0?-1===o&&(o=i):-1!==o&&(t.push({startIdx:o,endIdx:i-1}),o=-1);return-1!==o&&t.push({startIdx:o,endIdx:e.length-1}),t}(g).map(e=>g.slice(e.startIdx,e.endIdx+1).map(e=>{const t=it(e.azimuth,e.elevation,o);return{x:t.x*Ro,y:t.y*Ro,elev:e.elevation}})):[],x=[122,127,135],$=[245,197,24],k=e=>{const t=Math.sqrt(Math.max(0,Math.min(1,e/90))),o=x.map((e,o)=>Math.round(e+($[o]-e)*t));return`rgb(${o[0]},${o[1]},${o[2]})`},S=this.showSunPath&&this.showSunriseSunset?b.filter(e=>e.length>1).map((e,t)=>{const o=e[0],i=e[e.length-1],s=i.x-o.x,n=i.y-o.y,r=s*s+n*n||1,a=e.filter((t,o)=>o%6==0||o===e.length-1).map(e=>({offset:100*Math.max(0,Math.min(1,((e.x-o.x)*s+(e.y-o.y)*n)/r)),color:k(e.elev)}));return{id:`sun-path-grad-${t}`,x1:o.x,y1:o.y,x2:i.x,y2:i.y,stops:a}}):[],A=e=>this.showSunriseSunset?`url(#sun-path-grad-${e})`:"var(--warning-color, gold)",C=et(0,124,o),E=et(90,124,o),M=et(180,124,o),z=et(270,124,o),O=et(0,Ro,o),I=et(180,Ro,o),T=et(90,Ro,o),F=et(270,Ro,o),R=Ve("compass.sun_tooltip",{az:Ao(n),el:Ao(r)}),j=null!==m?Ve("compass.moon_tooltip",{phase:m.phaseName,pct:Math.round(100*m.fraction)}):"",N=Ve("compass.sun_path_tooltip");return G`
      <div class="compass">
        <svg viewBox="${-140} ${-140} ${280} ${280}">
          ${U`
            <defs>
              ${f?U`
                <mask id="moon-phase-mask">
                  <circle cx=${y} cy=${w} r=${6} fill="white"></circle>
                  <circle cx=${y+_} cy=${w} r=${6} fill="black"></circle>
                </mask>
              `:Y}
              ${S.map(e=>U`
                <linearGradient id=${e.id} gradientUnits="userSpaceOnUse"
                  x1=${e.x1} y1=${e.y1} x2=${e.x2} y2=${e.y2}>
                  ${e.stops.map(e=>U`<stop offset="${e.offset}%" stop-color=${e.color}></stop>`)}
                </linearGradient>
              `)}
            </defs>

            <circle class="grid" r=${Ro}></circle>
            <circle class="grid" r=${220/3}></circle>
            <circle class="grid" r=${Ro/3}></circle>
            <line class="grid thin" x1=${O.x} y1=${O.y} x2=${I.x} y2=${I.y}></line>
            <line class="grid thin" x1=${T.x} y1=${T.y} x2=${F.x} y2=${F.y}></line>

            ${t.map(e=>this._renderEntryLayers(e,i,o,g))}

            ${this.showSunPath&&b.length?U`<g ${_t(N)}>${b.filter(e=>e.length>1).flatMap((e,t)=>{const o=e.map(e=>`${e.x},${e.y}`).join(" "),i=U`<polyline class="sun-path-line" points=${o}
                        style="stroke:${A(t)}"></polyline>`,s=[];for(let t=0;t<e.length;t+=10){const o=e[t],i=e[Math.max(0,t-1)],n=e[Math.min(e.length-1,t+1)],r=180*Math.atan2(n.y-i.y,n.x-i.x)/Math.PI,a=this.showSunriseSunset?k(o.elev):"var(--warning-color, gold)";s.push(U`<path class="sun-path-chevron"
                          transform=${`translate(${o.x} ${o.y}) rotate(${r})`}
                          d="M -2.4 -3 L 1.8 0 L -2.4 3 L -0.7 0 Z"
                          style=${`fill:${a}`}></path>`)}return[i,...s]})}</g>`:Y}

            ${this.showCardinals?U`
              <text class="cardinal" x=${C.x} y=${C.y} text-anchor="middle" dominant-baseline="central">N</text>
              <text class="cardinal" x=${E.x} y=${E.y} text-anchor="middle" dominant-baseline="central">E</text>
              <text class="cardinal" x=${M.x} y=${M.y} text-anchor="middle" dominant-baseline="central">S</text>
              <text class="cardinal" x=${z.x} y=${z.y} text-anchor="middle" dominant-baseline="central">W</text>
            `:Y}

            ${f?U`
              <g ${_t(j)}>
                <circle class="moon-outline" cx=${y} cy=${w} r=${6}></circle>
                <image
                  class="moon-img"
                  href=${Fo}
                  x=${y-6}
                  y=${w-6}
                  width=${12}
                  height=${12}
                  mask="url(#moon-phase-mask)"
                ></image>
              </g>
            `:Y}

            <g ${_t(R)}>
              <circle class=${d} cx=${a.x*Ro} cy=${a.y*Ro} r="7"></circle>
            </g>
          `}
        </svg>
        ${this.showLegend?this._renderLegend(e,i,d,m):Y}
        ${this.showStats?this._renderStats(e,i):Y}
      </div>
    `}_renderEntryLayers(e,t,o=0,i=[]){const s=st(e.sun.window_azimuth),n=st(s-e.sun.fov_left),r=st(s+e.sun.fov_right),a=this._readActiveAzimuth(e.d.entities.start_sensor),l=this._readActiveAzimuth(e.d.entities.end_sensor),c=null!==a&&null!==l;let d,h;if(c)({wedgeStart:d,wedgeEnd:h}=function(e,t,o,i,s){const n=((o-i)%360+360)%360,r=i+s,a=((t-n)%360+360)%360,l=e=>e<=r?e:e-r<360-e?r:0,c=l(((e-n)%360+360)%360),d=l(a);return c===d?{wedgeStart:n,wedgeEnd:((n+r)%360+360)%360}:{wedgeStart:((n+Math.min(c,d))%360+360)%360,wedgeEnd:((n+Math.max(c,d))%360+360)%360}}(st(a),st(l),s,e.sun.fov_left,e.sun.fov_right));else{const t=function(e,t,o,i,s){if(void 0===s)return null;const n=st(t-o),r=o+i,a=e.filter(e=>((e.azimuth-n)%360+360)%360<=r&&e.elevation>s);return 0===a.length?null:{wedgeStart:a[0].azimuth,wedgeEnd:a[a.length-1].azimuth}}(i,s,e.sun.fov_left,e.sun.fov_right,e.sun.min_elevation);d=t?t.wedgeStart:n,h=t?t.wedgeEnd:r}const u=et(s,Ro,o),{outer:p,inner:g}=(m=e.sun.min_elevation,f=e.sun.max_elevation,_=Ro,void 0!==m&&void 0!==f&&m>f?{outer:_,inner:0}:{outer:void 0!==m?_*tt(m):_,inner:void 0!==f?_*tt(f):0});var m,f,_;const v=null!==e.coverPos?ct(e.coverPos,e.coverType,Ro,p):null,y=null!==e.actualPos?ct(e.actualPos,e.coverType,Ro,p):null,w=e.sun.blind_spot_range?[st((b=s)-(x=e.sun.blind_spot_range)[1]),st(b-x[0])]:null;var b,x;const $=w?ot(w[0],w[1],Ro,0,o):null,k=ot(d,h,p,g,o),S=c&&(d!==n||h!==r),A=S?ot(n,r,p,g,o):"",C=null!==v&&v>g?ot(d,h,v,g,o):"",E=null!==y&&y>g?ot(d,h,y,g,o):"",M=[];for(const t of xo(i,s,e.sun.fov_left,e.sun.fov_right)){const s=nt(i,t.startIdx,t.endIdx,e.sun.min_elevation);s&&!lt(s.wedgeStart,s.wedgeEnd,d,h)&&M.push({fov:ot(s.wedgeStart,s.wedgeEnd,p,g,o),cover:this.showCoverFill&&null!==v&&v>g?ot(s.wedgeStart,s.wedgeEnd,v,g,o):"",actual:this.showCoverFill&&null!==y&&y>g?ot(s.wedgeStart,s.wedgeEnd,y,g,o):"",from:s.wedgeStart,to:s.wedgeEnd})}const z=t?`${e.d.entry_title}: `:"",O=void 0!==e.sun.min_elevation||void 0!==e.sun.max_elevation?Ve("compass.elev_suffix",{min:Ao(e.sun.min_elevation??0),max:Ao(e.sun.max_elevation??90)}):"",I=c?`${z}${Ve("compass.active_sun_arc",{from:Ao(d),to:Ao(h),elev:O})}`:`${z}${Ve("compass.fov_arc",{left:Ao(e.sun.fov_left),right:Ao(e.sun.fov_right),elev:O})}`,T=`${z}${Ve("compass.window_normal_tooltip",{bearing:Ao(s)})}`,F=[];if(null!==e.coverPos){const t="cover_awning"===e.coverType?"compass.cover_position_target_awning":"compass.cover_position_target";F.push(`${z}${Ve(t,{pct:e.coverPos})}`),null!==e.actualPos&&F.push(Ve("compass.cover_position_actual",{pct:Math.round(e.actualPos)}))}const R=F.join("\n"),j=w?`${z}${Ve("compass.blind_spot",{from:Ao(w[0]),to:Ao(w[1])})}`:"",N=t||e.isOverride,P=t||e.isOverride,D=N?`fill: ${e.color}; stroke: ${e.color};`:"",K=P?`fill: ${e.color}; stroke: ${e.color};`:"",B=N?`fill: ${e.color}; stroke: ${e.color};`:"",W=N?`stroke: ${e.color};`:"",V=N?`fill: ${e.color};`:"",G=this.showCoverFill&&""!==C,L=this.showBlindSpot&&!!$,H=this.showWindowArrow,Q=`M 0 0 L ${u.x} ${u.y}`,q=N?`fill: ${e.color}; stroke: ${e.color};`:"",X=ht(u.x,u.y,s+o,9,5),J="display: none;",Z=`${z}${Ve("compass.fov_arc",{left:Ao(e.sun.fov_left),right:Ao(e.sun.fov_right),elev:O})}`;return U`<g class="entry-overlay">
      ${S?U`<g ${_t(Z)}>
              <path class="fov fov-static" style=${D} d=${A}></path>
            </g>`:Y}
      <g ${_t(I)}>
        <path class="fov" style=${D} d=${k}></path>
      </g>
      ${M.map(e=>{const t=`${z}${Ve("compass.active_sun_arc",{from:Ao(e.from),to:Ao(e.to),elev:O})}`;return U`<g ${_t(t)}>
          <path class="fov-extra" style=${D} d=${e.fov}></path>
          ${e.cover?U`<path class="cover-fill-extra" style=${K} d=${e.cover}></path>`:Y}
          ${e.actual?U`<path class="cover-actual-extra" style=${K} d=${e.actual}></path>`:Y}
        </g>`})}
      <g class="arrow-group" style=${H?"":J} ${_t(T)}>
        <path class="window" style=${W} d=${Q}></path>
        <path class="window-head" style=${q} d=${X}></path>
        <circle class="window-base" style=${V} cx="0" cy="0" r="4"></circle>
      </g>
      <g class="cover-group" style=${G?"":J} ${_t(R)}>
        <path class="cover-fill" style=${K} d=${C}></path>
        ${this.showCoverFill&&E?U`<path class="cover-actual" style=${K} d=${E}></path>`:Y}
      </g>
      <g class="blind-group" style=${L?"":J} ${_t(j)}>
        <path class="blind-spot" style=${B} d=${$??""}></path>
      </g>
    </g>`}_legendSunGlyph(e){return G`<span class="glyph"
      ><svg viewBox="-8 -8 16 16" width="20" height="20">
        ${U`<circle class=${e} cx="0" cy="0" r="5"></circle>`}
      </svg></span
    >`}_legendMoonGlyph(e){const t=e?dt(e.phase,4):0,o=this._legendMoonMaskId;return G`<span class="glyph"
      ><svg viewBox="-5 -5 10 10" width="11" height="11">
        ${U`
          <defs>
            <mask id=${o}>
              <circle cx="0" cy="0" r=${4} fill="white"></circle>
              <circle cx=${t} cy="0" r=${4} fill="black"></circle>
            </mask>
          </defs>
          <circle class="moon-outline" cx="0" cy="0" r=${4}></circle>
          <image
            class="moon-img"
            href=${Fo}
            x=${-4}
            y=${-4}
            width=${8}
            height=${8}
            mask=${`url(#${o})`}
          ></image>
        `}
      </svg></span
    >`}_legendWindowGlyph(e){const t=e?`stroke: ${e};`:"",o=e?`fill: ${e};`:"",i=ht(5,0,90,4,2);return G`<span class="glyph"
      ><svg class="window-glyph" viewBox="-6 -6 12 12" width="13" height="13">
        ${U`
          <line class="window" style=${t} x1="-5" y1="0" x2="1.5" y2="0"></line>
          <path class="window-head" style=${o} d=${i}></path>
        `}
      </svg></span
    >`}_renderLegend(e,t,o,i){const s=e[0]?.isOverride?e[0].color??null:null,n=e[0],r=null!==n?.coverPos&&null!=n?.actualPos&&void 0!==n?.coverPos&&Math.round(n.actualPos)!==Math.round(n.coverPos);return t?G`
        <div class="legend">
          <div>${this._legendSunGlyph(o)} ${Ve("compass.sun")}</div>
          ${this.showMoon?G`<div>${this._legendMoonGlyph(i)} ${Ve("compass.moon")}</div>`:Y}
          ${e.map(e=>G`
              <button
                type="button"
                class=${eo({"entry-toggle":!0,hidden:this._hiddenEntries.has(e.d.window_key)})}
                aria-pressed=${!this._hiddenEntries.has(e.d.window_key)}
                @click=${()=>this._toggleEntry(e.d.window_key)}
              >
                <span class="licell"
                  ><span class="swatch entry" style="background: ${e.color}"></span
                ></span>
                ${e.d.entry_title}
                ${e.sunInfront?G`<span class="status valid">${Ve("compass.in_fov_check")}</span>`:e.sun.in_fov?G`<span class="status in-fov">${Ve("compass.in_fov")}</span>`:G`<span class="status">${Ve("compass.none")}</span>`}
              </button>
            `)}
        </div>
      `:G`<div class="legend">
      <div>${this._legendSunGlyph(o)} ${Ve("compass.sun")}</div>
      ${this.showMoon?G`<div>${this._legendMoonGlyph(i)} ${Ve("compass.moon")}</div>`:Y}
      <div>
        <span class="licell"
          ><span
            class="swatch fov"
            style=${s?`background: ${s}`:""}
          ></span
        ></span>
        ${Ve("compass.window_fov")}
      </div>
      ${this.showCoverFill?G`<div>
            <span class="licell"
              ><span
                class="swatch cover-fill-swatch"
                style=${s?`background: ${s}`:""}
              ></span
            ></span>
            ${Ve("compass.cover_target")}
          </div>`:Y}
      ${this.showCoverFill&&r?G`<div>
            <span class="licell"
              ><span
                class="swatch cover-actual-swatch"
                style=${s?`border-color: ${s}`:""}
              ></span
            ></span>
            ${Ve("compass.cover_held")}
          </div>`:Y}
      ${this.showWindowArrow?G`<div>${this._legendWindowGlyph(s)} ${Ve("compass.window_normal")}</div>`:Y}
    </div>`}_renderStats(e,t){const o=e[0],i=o.sunAzi,s=o.sun.elevation,{latitude:n,longitude:r}=this.hass.config,a=this.showMoon&&void 0!==n&&void 0!==r?$o(n,r):null;return t?G`
        <div class="stats dim">
          <div class="stats-row">
            <span
              >${Ve("compass.stat_sun")}${Ao(i)} / ${Ao(s)}</span
            >
            ${this.showMoon&&a?G`<span>${a.phaseName} ${Math.round(100*a.fraction)}%</span>`:Y}
          </div>
          ${e.map(e=>G`
              <div class="stats-row entry-row">
                <span class="swatch entry" style="background: ${e.color}"></span>
                <span class="entry-name">${e.d.entry_title}</span>
                <span>∠${Ao(e.sun.gamma)}</span>
                <span>W ${Ao(st(e.sun.window_azimuth))}</span>
                ${e.sun.in_fov?G`<span class="status in-fov" ${_t(Ve("compass.in_fov_tooltip"))}
                      >✓</span
                    >`:Y}
              </div>
            `)}
        </div>
      `:G`<div class="stats dim">
      <span>${Ve("compass.stat_azi")}${Ao(i)}</span>
      <span>${Ve("compass.stat_elev")}${Ao(s)}</span>
      <span>∠: ${Ao(o.sun.gamma)}</span>
      <span
        >${Ve("compass.stat_window")}${Ao(st(o.sun.window_azimuth))}</span
      >
      ${this.showMoon&&a?G`<span>${a.phaseName} ${Math.round(100*a.fraction)}%</span>`:Y}
    </div>`}};function Po(e){let t=null,o=null;const i=6e4-Date.now()%6e4;return t=setTimeout(()=>{t=null,e(),o=setInterval(e,6e4)},i),()=>{null!==t&&(clearTimeout(t),t=null),null!==o&&(clearInterval(o),o=null)}}No.styles=r`
    :host {
      display: block;
      width: 100%;
      container-type: inline-size;
    }
    .compass {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
    }
    /* Plot SVG only — scoped to the direct child of .compass so these sizing
       rules never cascade onto the small inline legend glyph SVGs (which size
       themselves via their width/height attributes). */
    .compass > svg {
      width: 100%;
      max-width: 260px;
      height: auto;
      display: block;
    }
    :host([compact]) .compass > svg {
      max-width: 180px;
    }
    :host([compact]) .legend {
      display: none;
    }
    @container (min-width: 320px) {
      .compass {
        flex-direction: row;
        flex-wrap: wrap;
        align-items: center;
        justify-content: center;
        gap: 16px;
      }
      .compass > svg {
        max-width: none;
        flex: 1 1 0;
        min-width: 200px;
      }
      :host([compact]) .compass > svg {
        max-width: 280px;
      }
      .compass .legend,
      .compass .stats {
        flex: 0 1 auto;
        min-width: 0;
        flex-direction: column;
        align-items: flex-start;
        justify-content: center;
      }
      /* Match the stats column's row rhythm to the legend's so the two side-by-
         side columns share the same vertical spacing: same row gap as .legend
         (12px) and the same per-row height as the legend's 20px icon cell, with
         the stat text vertically centred in that height. */
      .compass .stats {
        gap: 12px;
      }
      .compass .stats-row,
      .compass .stats > span {
        justify-content: flex-start;
        min-height: 20px;
        display: flex;
        align-items: center;
      }
    }
    .grid {
      fill: none;
      stroke: var(--divider-color);
      stroke-width: 1;
    }
    .grid.thin {
      stroke-width: 0.5;
      opacity: 0.5;
    }
    .fov,
    .fov-extra {
      /* Default (single-entry, no override): a lighter, more-transparent shade
         of the cover colour — same identity as the cover wedge, just fainter —
         matching how multi-entry/override mode already colours the FOV. Keeping
         it off gold lets the gold sun dot read clearly against it. */
      fill: var(--primary-color);
      fill-opacity: 0.22;
      stroke: var(--primary-color);
      stroke-width: 1;
      stroke-opacity: 0.7;
      transition:
        fill 0.3s ease,
        fill-opacity 0.3s ease,
        stroke 0.3s ease,
        stroke-opacity 0.3s ease;
    }
    /* Static FOV envelope shown dim beneath the active sun arc — lets the
       reader see the configured ±fov_left/right span at the same time as
       today's reachable sub-arc. */
    .fov.fov-static {
      fill-opacity: 0.07;
      stroke-opacity: 0.25;
      stroke-dasharray: 4 3;
    }
    .cover-fill,
    .cover-fill-extra {
      fill: var(--primary-color);
      fill-opacity: 0.3;
      stroke: var(--primary-color);
      stroke-width: 1;
      stroke-opacity: 0.6;
      transition:
        fill 0.3s ease,
        fill-opacity 0.3s ease,
        stroke 0.3s ease,
        stroke-opacity 0.3s ease;
    }
    /* Live/actual cover position drawn over the solid target wedge: same fill
       colour but fainter and dashed, so when actual == target it disappears
       into the target wedge and only a divergence reads as a second ring. */
    .cover-actual,
    .cover-actual-extra {
      fill: var(--primary-color);
      fill-opacity: 0.15;
      stroke: var(--primary-color);
      stroke-width: 1;
      stroke-opacity: 0.6;
      stroke-dasharray: 3 2;
      transition:
        fill 0.3s ease,
        fill-opacity 0.3s ease,
        stroke 0.3s ease,
        stroke-opacity 0.3s ease;
    }
    .blind-spot {
      fill: var(--error-color, crimson);
      fill-opacity: 0.12;
      stroke: var(--error-color, crimson);
      stroke-dasharray: 3 3;
    }
    .window {
      fill: none;
      stroke: var(--primary-color);
      stroke-width: 3;
      stroke-linecap: round;
    }
    .window-base {
      fill: var(--primary-color);
    }
    .cardinal {
      font-size: 12px;
      fill: var(--secondary-text-color);
      font-weight: 500;
    }
    .sun {
      fill: var(--secondary-text-color);
      transition: fill 0.3s ease;
    }
    .sun.up {
      /* outside FOV, above horizon — light yellow */
      fill: #ffe680;
    }
    .sun.in-fov {
      /* in FOV but not hitting — plain gold (no glow) */
      fill: var(--warning-color, gold);
    }
    .sun.valid {
      fill: var(--warning-color, gold);
      filter: drop-shadow(0 0 4px var(--warning-color, gold));
    }
    .sun.night {
      /* below horizon — dim grey */
      fill: var(--secondary-text-color);
      opacity: 0.55;
    }
    .legend {
      display: flex;
      gap: 12px;
      font-size: 0.75rem;
      color: var(--secondary-text-color);
      flex-wrap: wrap;
      justify-content: center;
    }
    /* Centre each glyph/swatch row against its label so larger glyphs (the sun)
       stay vertically aligned — vertical-align:middle drifts as the glyph grows.
       The cover-entry rows are buttons that already do this; these are the
       plain sun/moon/window/FOV rows. The glyph/swatch margin-right keeps the
       gap between icon and text. */
    .legend > div {
      display: flex;
      align-items: center;
    }
    button.entry-toggle {
      background: none;
      border: 0;
      padding: 0;
      color: inherit;
      font: inherit;
      cursor: pointer;
      display: flex;
      align-items: center;
    }
    button.entry-toggle.hidden {
      opacity: 0.45;
      text-decoration: line-through;
    }
    .legend .status {
      margin-left: 4px;
      opacity: 0.8;
    }
    .legend .status.valid {
      color: var(--warning-color, gold);
    }
    .legend .status.in-fov {
      color: var(--state-active-color, orange);
    }
    .dot,
    .swatch {
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      vertical-align: middle;
    }
    .swatch.fov {
      background: var(--warning-color, gold);
      opacity: 0.4;
      border-radius: 2px;
    }
    .swatch.entry {
      border-radius: 2px;
      opacity: 0.9;
    }
    /* Uniform fixed-width icon cell shared by every legend row's leading icon —
       glyph wrappers (.glyph: live sun, phased moon, window arrow) and swatch
       wrappers (.licell). Centring each icon in a constant-width cell keeps all
       labels left-aligned in a column even though the glyphs differ in size
       (the sun is intentionally the largest). The cell is a fixed flex item of
       the flex legend rows; overflow stays visible so the sun's glow isn't
       clipped. */
    .glyph,
    .licell {
      flex: 0 0 20px;
      height: 20px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-right: 6px;
    }
    .glyph svg {
      /* Size comes from each glyph's own width/height attributes; display:block
         inside the inline-block wrapper avoids inline-descender spacing. The
         explicit min/max-width reset guards against any ancestor svg rule. */
      display: block;
      overflow: visible;
      min-width: 0;
      max-width: none;
    }
    /* The legend arrow reuses the plot's .window stroke colour but the plot's
       stroke-width: 3 is far too heavy for the 12-unit glyph viewBox — scope a
       proportional shaft width here so it reads as a slim arrow, not a blob. */
    .window-glyph .window {
      stroke-width: 1.6;
    }
    /* Arrowhead on the legend window-azimuth glyph (and matched on the plotted
       window line); follows the override colour via inline style when set. */
    .window-head {
      fill: var(--primary-color);
    }
    .swatch.cover-fill-swatch {
      background: var(--primary-color);
      /* The cover wedge is drawn ON TOP of the FOV wedge in the same arc, so the
         visible cover region is the two fills composited: the FOV's 0.22 plus the
         cover's 0.30 → 1 − (1−0.22)(1−0.30) ≈ 0.45. Matching that here keeps the
         legend swatch the same darker shade the reader sees in the plot. */
      opacity: 0.45;
      border-radius: 2px;
    }
    /* Mirrors the dashed, faint .cover-actual held ring: a near-transparent fill
       inside a dashed primary-colour border, so the legend swatch reads like the
       second (held) ring rather than the solid target wedge (#158). */
    .swatch.cover-actual-swatch {
      background: color-mix(in srgb, var(--primary-color) 15%, transparent);
      border: 1px dashed var(--primary-color);
      border-radius: 2px;
      box-sizing: border-box;
    }
    .dot.rise-dot {
      background: var(--warning-color, gold);
      opacity: 0.75;
    }
    .dot.set-dot {
      background: var(--secondary-text-color);
      opacity: 0.55;
    }
    .stats {
      display: flex;
      flex-direction: column;
      gap: 4px;
      font-size: 0.78rem;
      align-items: center;
    }
    .stats-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: center;
    }
    .entry-row .entry-name {
      font-weight: 500;
      color: var(--primary-text-color);
    }
    .entry-row .status.in-fov {
      color: var(--state-active-color, orange);
    }
    .dim {
      color: var(--secondary-text-color);
    }
    .placeholder {
      color: var(--secondary-text-color);
      text-align: center;
      padding: 20px;
    }
    /* The sun path is a thin spine + directional block-arrow chevrons per
       above-horizon run. The spine carries the per-run gradient (sunrise gold →
       sunset grey, see sunPathGradients in render) and sits faint beneath the
       chevrons, which point in the direction of the sun's travel. */
    .sun-path-line {
      fill: none;
      stroke-width: 1;
      stroke-linecap: round;
      opacity: 0.45;
    }
    .sun-path-chevron {
      stroke: none;
      opacity: 0.95;
    }
    .moon-outline {
      fill: none;
      stroke: var(--secondary-text-color);
      stroke-width: 0.8;
      opacity: 0.5;
    }
    /* Photographic moon disc, clipped to the lit fraction by moon-phase-mask. */
    .moon-img {
      opacity: 0.95;
    }
    /* Floating-tooltip cursor lifecycle: a help cursor hints "there's more
       here" on hover (SVG groups + the in-FOV status pip), flipping to default
       the moment OUR bubble appears. */
    [data-tooltip]:hover {
      cursor: help;
    }
    [data-tooltip][acp-tt-shown] {
      cursor: default;
    }
  `,e([ge({attribute:!1})],No.prototype,"hass",void 0),e([ge({attribute:!1})],No.prototype,"discovered_list",void 0),e([ge({type:Boolean,reflect:!0})],No.prototype,"compact",void 0),e([ge({attribute:!1})],No.prototype,"showStats",void 0),e([ge({attribute:!1})],No.prototype,"showLegend",void 0),e([ge({attribute:!1})],No.prototype,"showMoon",void 0),e([ge({attribute:!1})],No.prototype,"showCardinals",void 0),e([ge({attribute:!1})],No.prototype,"showBlindSpot",void 0),e([ge({attribute:!1})],No.prototype,"showSunPath",void 0),e([ge({attribute:!1})],No.prototype,"showSunriseSunset",void 0),e([ge({attribute:!1})],No.prototype,"showCoverFill",void 0),e([ge({attribute:!1})],No.prototype,"showWindowArrow",void 0),e([ge({attribute:!1})],No.prototype,"coverColors",void 0),e([ge({attribute:!1})],No.prototype,"northOffsetDeg",void 0),e([me()],No.prototype,"_hiddenEntries",void 0),No=e([he("acp-sky-compass")],No);const Do=32,Ko=864e5;function Bo(e){if(!e)return null;const t=new Date(e);return Number.isNaN(t.getTime())?null:t}let Wo=class extends ce{constructor(){super(...arguments),this.discoveredList=[],this.coverColors=[],this.compact=!1,this._cancelMinuteTimer=null}connectedCallback(){super.connectedCallback(),this._cancelMinuteTimer=Po(()=>this.requestUpdate())}disconnectedCallback(){super.disconnectedCallback(),this._cancelMinuteTimer?.(),this._cancelMinuteTimer=null}shouldUpdate(e){if(e.size>1||!e.has("hass"))return!0;const t=e.get("hass"),o=[];for(const e of this.discoveredList){const t=e.entities;o.push(t.target_position_sensor,t.sun_infront_binary)}return fe(t,this.hass,o)}_sunAttrsFor(e){return so(this.hass,e)}_sunDotTraceInputs(){const e=this.discoveredList[0]?.entities.sun_infront_binary;return{sunState:null,directSunValid:!!e&&"on"===this.hass.states[e]?.state}}_scheduleBounds(){const e=this.discoveredList[0]?.entities.control_status_sensor;if(!e)return null;const t=this.hass.states[e]?.attributes;return t?{start:Bo(t.schedule_start),end:Bo(t.schedule_end)}:null}render(){if(!this.hass||0===this.discoveredList.length)return Y;const e=this._sunAttrsFor(this.discoveredList[0]),{latitude:t,longitude:o,time_zone:i}=this.hass.config??{};if(void 0===t||void 0===o||!e)return G`<div class="placeholder">${Ve("elevation.placeholder")}</div>`;const s=wo(i),n=vo(t,o,s),r=new Date,a=e=>{const t=e.getTime()-s.getTime();return Do+t/864e5*360},l=e=>138-(e- -10)/100*128,c=n.map(e=>`${a(e.t).toFixed(1)},${l(e.elevation).toFixed(1)}`).join(" "),d=l(0),h=a(r),u=this._interpAt(n,r),p=u?l(u.elevation):null,g=!u||u.elevation<=0,m=this._sunDotTraceInputs(),f=Mo[zo({belowHorizon:g,sunState:m.sunState,directSunValid:m.directSunValid,inFov:!0===e.in_fov})].replace(/^sun /,""),_=e=>138-128*e,v=this.discoveredList.length>1,y=this._scheduleBounds(),w=y?function(e,t,o,i){if(!e&&!t)return{offSchedule:[],bars:[]};const s=e=>(e.getTime()-o)/i,n=e=>Math.max(0,Math.min(1,e)),r=e=>n(e),a=e=>e>1?e-Math.floor(e):n(e),l=e=>e>0&&e<1?[e]:[];if(e&&!t){const t=s(e);return{offSchedule:[{x0:0,x1:r(t)}],bars:l(t)}}if(!e&&t){const e=s(t);return{offSchedule:[{x0:a(e),x1:1}],bars:l(e)}}const c=s(e),d=s(t),h=r(c),u=a(d),p=[...l(c),...l(d)];if(h>u)return{offSchedule:[{x0:u,x1:h}],bars:p};const g=[];return h>0&&g.push({x0:0,x1:h}),u<1&&g.push({x0:u,x1:1}),{offSchedule:g,bars:p}}(y.start,y.end,s.getTime(),Ko):{offSchedule:[],bars:[]},b=e=>Do+360*e,x=w.offSchedule.map(e=>({x:b(e.x0),width:b(e.x1)-b(e.x0)})),$=y?.start&&s?(y.start.getTime()-s.getTime())/Ko:null,k=w.bars.map(e=>{const t=null!==$&&Math.abs(e-$)<1e-9?y.start.toISOString():y.end.toISOString(),o=null!==$&&Math.abs(e-$)<1e-9,s=b(e);return{x:s,anchor:s>=391?"end":s<=33?"start":"middle",label:Co(t,i),tooltip:Ve(o?"elevation.schedule_start_tooltip":"elevation.schedule_end_tooltip")}}),S=(()=>{if(!y)return null;const e=y.start?Co(y.start.toISOString(),i):null,t=y.end?Co(y.end.toISOString(),i):null;return e&&t?Ve("elevation.schedule",{from:e,to:t}):e?Ve("elevation.schedule_from",{from:e}):t?Ve("elevation.schedule_until",{to:t}):null})(),A=this.discoveredList.map((e,t)=>{const o=this._sunAttrsFor(e),{color:s,isOverride:r}=To(this.coverColors?.[t],t),l=r;if(!o)return{d:e,runs:[],inPlotBands:[],runBars:[],label:"",color:s,inlineFill:l};const c=xo(n,o.window_azimuth,o.fov_left,o.fov_right),d="number"==typeof o.min_elevation,h="number"==typeof o.max_elevation,{loFrac:u,hiFrac:p}=function(e,t){if(void 0!==e&&void 0!==t&&e>t)return{loFrac:0,hiFrac:1};const o=e=>Math.max(0,Math.min(1,(e- -10)/100));return{loFrac:void 0!==e?o(e):0,hiFrac:void 0!==t?o(t):1}}(o.min_elevation,o.max_elevation),g=d||h?_(p):10,m=d||h?_(u):138,f=g,y=Math.max(0,m-g),w=c.map(e=>({x0:a(n[e.startIdx].t),x1:a(n[e.endIdx].t),y:f,height:y})),b=c.map(e=>({x0:a(n[e.startIdx].t),x1:a(n[e.endIdx].t),range:`${Co(n[e.startIdx].t.toISOString(),i)} → ${Co(n[e.endIdx].t.toISOString(),i)}`})),x=c.map(e=>`${Co(n[e.startIdx].t.toISOString(),i)} → ${Co(n[e.endIdx].t.toISOString(),i)}`).join(", "),$=[];return v||(d&&$.push(m),h&&$.push(g)),{d:e,runs:c,inPlotBands:w,runBars:b,label:x,color:s,inlineFill:l,limitLines:$}}),C=A.some(e=>e.runs.length>0),E=v?function(e){if(e<=0)return{rows:[],height:0};const t=Array.from({length:e},(e,t)=>({y:0+11*t,height:8}));return{rows:t,height:0+8*e+3*(e-1)+0}}(A.length):{rows:[],height:0},M=138-E.height-3;return G`
      <div class="wrap">
        <div class="head">
          <span class="label">${Ve("elevation.title")}</span>
          <span class="head-meta">
            ${v?Y:C?G`<span class="dim"
                      >${Ve("elevation.fov_windows",{windows:A[0].label})}</span
                    >`:G`<span class="dim">${Ve("elevation.no_fov_today")}</span>`}
            ${S?G`<span class="dim schedule">${S}</span>`:Y}
          </span>
        </div>
        <svg viewBox="0 0 ${400} ${160}" preserveAspectRatio="none">
          ${U`
            <!-- y-axis gridlines -->
            ${[0,30,60,90].map(e=>U`
              <line class="grid" x1=${Do} y1=${l(e)} x2=${392} y2=${l(e)} />
              <text class="tick" x=${28} y=${l(e)+3} text-anchor="end">${e}°</text>
            `)}

            <!-- horizon -->
            <line class="horizon" x1=${Do} y1=${d} x2=${392} y2=${d} />

            <!-- elevation limit gridlines (single-window legacy path only) -->
            ${A.flatMap(e=>(e.limitLines??[]).map(e=>U`<line class="limit-line" x1=${Do} y1=${e} x2=${392} y2=${e} />`))}

            <!-- In-plot FOV bands: single-window legacy path only. -->
            ${v?Y:A.flatMap(e=>e.inPlotBands.map(t=>U`<rect
                        class="fov-band"
                        x=${t.x0}
                        y=${t.y}
                        width=${t.x1-t.x0}
                        height=${t.height}
                        style=${e.inlineFill?`fill:${e.color}`:Y}
                      />`))}

            <!-- Per-window FOV ribbon (multi-window only): one row per window,
                 a faint full-width track plus color-keyed bars for in-FOV runs,
                 sharing the plot's xAt() time scale. Overlaid as a band anchored
                 to the bottom of the plot; drawn BEFORE the curve so the blue
                 curve stays crisp on top. -->
            ${E.rows.flatMap((e,t)=>{const o=A[t],i=M+e.y,s=o.runs.length?o.d.entry_title:Ve("elevation.fov_window_named",{name:o.d.entry_title,windows:Ve("elevation.no_fov_today")}),n=U`<rect
                class="ribbon-track"
                x=${Do}
                y=${i}
                width=${360}
                height=${e.height}
                rx="2"
                ${_t(s)}
              ></rect>`,r=o.runBars.map(t=>U`<rect
                  class="ribbon-bar"
                  x=${t.x0}
                  y=${i}
                  width=${t.x1-t.x0}
                  height=${e.height}
                  rx="2"
                  style=${`fill:${o.color}`}
                  ${_t(Ve("elevation.fov_window_named",{name:o.d.entry_title,windows:t.range}))}
                ></rect>`);return[n,...r]})}

            <!-- Schedule window overlay (issue #128): faint off-schedule gray
                 zone(s) + thin start/end bars with a clock-time tick. Rendered
                 PRE-CURVE so the sun curve and now-line paint on top. The tick
                 label sits slightly higher than the axis ticks (its own class)
                 so it doesn't read as an axis tick. -->
            ${x.map(e=>U`<rect
                class="off-schedule-zone"
                x=${e.x}
                y=${10}
                width=${e.width}
                height=${128}
              />`)}
            ${k.flatMap(e=>[U`<line
                class="schedule-bar"
                x1=${e.x}
                y1=${10}
                x2=${e.x}
                y2=${138}
                ${_t(e.tooltip)}
              ></line>`,U`<text
                class="schedule-tick"
                x=${e.x}
                y=${17}
                text-anchor=${e.anchor}
              >${e.label}</text>`])}

            <!-- elevation curve (drawn after the ribbon so it sits on top) -->
            <polyline class="curve" points=${c} />

            <!-- current-time cursor + sun dot, drawn last so they sit on top of
                 the curve AND the ribbon bars. A wide transparent hit-line widens
                 the hover target so the thin now-line is easy to tooltip. -->
            <g class="now-group" ${_t(Co(r.toISOString(),i))}>
              <line class="now-hit" x1=${h} y1=${10} x2=${h} y2=${138} />
              <line class="now" x1=${h} y1=${10} x2=${h} y2=${138} />
            </g>
            ${null!==p?U`<circle class="sun-dot ${f}" cx=${h} cy=${p} r="4" />`:Y}

            <!-- x-axis gridlines + time labels at every 6h, drawn last so the
                 axis sits on the topmost layer (nothing paints over the times).
                 Edge labels anchor inward (start at 00:00, end at 24:00) so they
                 don't clip past the viewBox. -->
            ${[0,6,12,18,24].map(e=>{const t=new Date(s.getTime()+36e5*e),o=0===e?"start":24===e?"end":"middle";return U`
                <line class="grid faint" x1=${a(t)} y1=${10} x2=${a(t)} y2=${138} />
                <text class="tick" x=${a(t)} y=${152} text-anchor=${o}>${e.toString().padStart(2,"0")}:00</text>
              `})}
          `}
        </svg>
      </div>
    `}_interpAt(e,t){if(0===e.length)return null;const o=t.getTime();if(o<=e[0].t.getTime())return e[0];if(o>=e[e.length-1].t.getTime())return e[e.length-1];for(let i=1;i<e.length;i++)if(e[i].t.getTime()>=o){const s=e[i-1],n=e[i],r=(o-s.t.getTime())/(n.t.getTime()-s.t.getTime());return{t:t,elevation:s.elevation+(n.elevation-s.elevation)*r,azimuth:s.azimuth+(n.azimuth-s.azimuth)*r}}return e[e.length-1]}};function Vo(e){return String(e??"").trim().toLowerCase()}function Go(e,t,o,i=Oe,s=null){const n=i[Vo(o)]??o,r=null!==s?` ${So(s)}`:"",a=t.reason??(e.length>0?e[e.length-1].reason:"");return a?`${n}${r} — ${a}`:`${n}${r}`.trimEnd()}Wo.styles=r`
    :host {
      display: block;
      width: 100%;
      min-width: 0;
    }
    .wrap {
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 0;
    }
    .head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      font-size: 0.78rem;
      color: var(--secondary-text-color);
    }
    .label {
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }
    .head-meta {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 1px;
      text-align: right;
    }
    svg {
      width: 100%;
      height: auto;
      aspect-ratio: 400 / 160;
      display: block;
    }
    :host([compact]) svg {
      aspect-ratio: 400 / 110;
    }
    :host([compact]) .head {
      display: none;
    }
    .grid {
      stroke: var(--divider-color);
      stroke-width: 0.5;
      opacity: 0.6;
    }
    .grid.faint {
      opacity: 0.25;
    }
    .tick {
      font-size: 9px;
      fill: var(--secondary-text-color);
    }
    .horizon {
      stroke: var(--divider-color);
      stroke-width: 1;
      stroke-dasharray: 2 2;
    }
    .limit-line {
      stroke: var(--warning-color, gold);
      stroke-width: 1;
      stroke-dasharray: 4 3;
      opacity: 0.7;
    }
    .fov-band {
      /* Lighter shade of the cover colour (not gold), so the gold sun-dot reads
         clearly against it. Matches the sky-compass .fov default. */
      fill: var(--primary-color);
      fill-opacity: 0.18;
    }
    .off-schedule-zone {
      fill: var(--divider-color);
      fill-opacity: 0.12;
      pointer-events: none;
    }
    /* Floating-tooltip cursor lifecycle: help hint on hover, default once OUR
       bubble is shown. Applies to every tooltip carrier (schedule bar, ribbon
       track/bar, now-cursor group). */
    [data-tooltip]:hover {
      cursor: help;
    }
    [data-tooltip][acp-tt-shown] {
      cursor: default;
    }
    .schedule-bar {
      stroke: var(--divider-color);
      stroke-width: 1;
    }
    .schedule-tick {
      font-size: 8px;
      fill: var(--secondary-text-color);
    }
    .ribbon-track {
      fill: var(--divider-color);
      fill-opacity: 0.25;
    }
    .ribbon-bar {
      /* Fallback only — the ribbon always sets an inline per-window fill. Kept on
         the cover colour for consistency with the FOV band. */
      fill: var(--primary-color);
      fill-opacity: 0.85;
    }
    .curve {
      fill: none;
      stroke: var(--primary-color);
      stroke-width: 2;
      stroke-linejoin: round;
      stroke-linecap: round;
    }
    .now {
      stroke: var(--accent-color, crimson);
      stroke-width: 1.25;
      pointer-events: none;
    }
    .now-hit {
      stroke: transparent;
      stroke-width: 10;
    }
    /* Colour states mirror acp-sky-compass .sun.* so the sun reads the same
       across both visuals. */
    .sun-dot {
      fill: var(--secondary-text-color);
      transition: fill 0.3s ease;
    }
    .sun-dot.up {
      /* outside FOV, above horizon — light yellow */
      fill: #ffe680;
    }
    .sun-dot.in-fov {
      /* in FOV but not hitting — plain gold (no glow) */
      fill: var(--warning-color, gold);
    }
    .sun-dot.valid {
      fill: var(--warning-color, gold);
      filter: drop-shadow(0 0 3px var(--warning-color, gold));
    }
    .sun-dot.night {
      /* below horizon — dim grey */
      fill: var(--secondary-text-color);
      opacity: 0.55;
    }
    .dim {
      color: var(--secondary-text-color);
    }
    .placeholder {
      color: var(--secondary-text-color);
      text-align: center;
      padding: 20px;
    }
  `,e([ge({attribute:!1})],Wo.prototype,"hass",void 0),e([ge({attribute:!1})],Wo.prototype,"discoveredList",void 0),e([ge({attribute:!1})],Wo.prototype,"coverColors",void 0),e([ge({type:Boolean,reflect:!0})],Wo.prototype,"compact",void 0),Wo=e([he("acp-elevation-chart")],Wo);let Uo=class extends ce{constructor(){super(...arguments),this.compact=!1,this.showSummary=!0,this.hideInactive=!1}shouldUpdate(e){if(e.size>1||!e.has("hass"))return!0;const t=e.get("hass"),o=this.discovered?.entities;return fe(t,this.hass,[o?.target_position_sensor])}_winnerLabel(e){const t=Vo(e);return function(e){return ze.includes(e)}(t)?Ve(Ie[t]):e}render(){if(!this.hass||!this.discovered)return Y;const e=io(this.hass,this.discovered);if(!e||0===e.trace.length)return G`<div class="placeholder">${Ve("decision.placeholder")}</div>`;const t=this._winnerLabel(e.winner),o=Go(e.trace,e,e.winner,this._labels(),ro(this.hass,this.discovered)),i=this.hideInactive?e.trace.slice(-1):e.trace;return G`
      <div class="wrap">
        <div class="head">
          <span class="label">${Ve("decision.pipeline")}</span>
          <span class="winner">${Ve("decision.winner",{name:t})}</span>
        </div>
        ${this.showSummary&&o?G`<div class="summary" ${_t(Ve("decision.summary_tooltip"))}>${o}</div>`:Y}
        <div class="rows">${i.map((e,t)=>this._row(e,t))}</div>
      </div>
    `}_labels(){const e={};for(const[t,o]of Object.entries(Ie))e[t]=Ve(o);return e}_row(e,t){return G`
      <div class="row ${e.matched?"winner":"match"}">
        <span class="idx dim">${t+1}</span>
        <span class="reason-inline">${e.handler}</span>
        ${e.matched?G`<span class="badge">✓</span>`:Y}
      </div>
    `}};var Lo,Yo;Uo.styles=r`
    :host {
      display: block;
    }
    /* Floating-tooltip cursor lifecycle: a help cursor hints "there's more
       here" on hover, flipping to default the moment OUR bubble appears. */
    [data-tooltip]:hover {
      cursor: help;
    }
    [data-tooltip][acp-tt-shown] {
      cursor: default;
    }
    .wrap {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .head {
      display: flex;
      justify-content: space-between;
      font-size: 0.78rem;
      color: var(--secondary-text-color);
      margin-bottom: 2px;
    }
    .label {
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }
    .rows {
      display: flex;
      flex-direction: column;
      gap: 1px;
    }
    .row {
      display: grid;
      grid-template-columns: 20px 1fr auto;
      align-items: center;
      gap: 6px;
      padding: 3px 6px;
      border-radius: 4px;
      font-size: 0.8rem;
      line-height: 1.3;
    }
    :host([compact]) .row {
      grid-template-columns: 16px 1fr auto;
      font-size: 0.72rem;
      padding: 1px 4px;
    }
    :host([compact]) .head {
      display: none;
    }
    .row.match {
      background: rgba(255, 193, 7, 0.08);
    }
    .row.winner {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
      font-weight: 600;
    }
    .row.winner .dim {
      color: inherit;
      opacity: 0.85;
    }
    .idx {
      font-variant-numeric: tabular-nums;
      text-align: right;
    }
    .reason-inline {
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .badge {
      font-weight: 700;
      padding-left: 4px;
    }
    .summary {
      font-size: 0.85rem;
      line-height: 1.3;
      padding: 2px 4px 4px;
      color: var(--primary-text-color);
    }
    :host([compact]) .summary {
      font-size: 0.75rem;
      padding: 0 2px 2px;
    }
    .dim {
      color: var(--secondary-text-color);
    }
    .placeholder {
      color: var(--secondary-text-color);
      padding: 16px;
      text-align: center;
    }
  `,e([ge({attribute:!1})],Uo.prototype,"hass",void 0),e([ge({attribute:!1})],Uo.prototype,"discovered",void 0),e([ge({type:Boolean,reflect:!0})],Uo.prototype,"compact",void 0),e([ge({type:Boolean,reflect:!0,attribute:"show-summary"})],Uo.prototype,"showSummary",void 0),e([ge({type:Boolean,reflect:!0,attribute:"hide-inactive"})],Uo.prototype,"hideInactive",void 0),Uo=e([he("acp-decision-strip")],Uo),function(e){e.language="language",e.system="system",e.comma_decimal="comma_decimal",e.decimal_comma="decimal_comma",e.space_comma="space_comma",e.none="none"}(Lo||(Lo={})),function(e){e.language="language",e.system="system",e.am_pm="12",e.twenty_four="24"}(Yo||(Yo={}));const Ho=["closed","locked","off"],Qo=(e,t,o,i)=>{i=i||{},o=null==o?{}:o;const s=new Event(t,{bubbles:void 0===i.bubbles||i.bubbles,cancelable:Boolean(i.cancelable),composed:void 0===i.composed||i.composed});return s.detail=o,e.dispatchEvent(s),s},qo=e=>{Qo(window,"haptic",e)};function Xo(e){return void 0!==e&&"none"!==e.action}function Jo(e,t,o){return e.filter(e=>"off"===e||("solar"===e?function(e){return e.solarMatched}(o)&&!1!==t?.solar:!1!==t?.[e]))}function Zo(e){if(!1===e.integrationEnabled)return"off";if(e.manualActive)return"manual";const t=Vo(e.winner);return je[t]??"auto"}function ei(e,t){return{solarMatched:"calculated"===Vo(t)}}function ti(e){const t=null!=e&&Number.isFinite(e)?Ve("overrides.resume_confirm_pos",{position:String(Math.round(e))}):Ve("overrides.resume_confirm");return window.confirm(t)}function oi(e,t){if(!e||!t)return null;const o=parseFloat(e.states[t]?.state??"");return Number.isNaN(o)?null:o}let ii=class extends ce{constructor(){super(...arguments),this.winner="default",this.compact=!1,this.integrationEnabled=!0,this.manualActive=!1,this.resumable=!1}render(){const e=this._kind(),t=Ne[e],o=Ve(Pe[e]),i=De[e],s=G`${i?G`<ha-icon class="badge-icon" icon=${i}></ha-icon>`:Y}${o}${this.resumable?G`<ha-icon class="resume-icon" icon="mdi:restore"></ha-icon>`:Y}`;if(this.resumable){const o=Ve("tile.resume_aria");return G`<button
        class="badge kind-${e} resumable"
        style="background:${t.bg};color:${t.fg};"
        part="badge"
        type="button"
        ${_t(o)}
        aria-label=${o}
        @click=${this._onResumeClick}
        @pointerdown=${this._stop}
      >
        ${s}
      </button>`}return G`<span
      class="badge kind-${e}"
      style="background:${t.bg};color:${t.fg};"
      part="badge"
      >${s}</span
    >`}_stop(e){e.stopPropagation()}_onResumeClick(e){e.stopPropagation(),this.dispatchEvent(new CustomEvent("acp-resume",{bubbles:!0,composed:!0}))}_kind(){return this.kindOverride??Zo({winner:this.winner,integrationEnabled:this.integrationEnabled,manualActive:this.manualActive})}};function si(e){const t=e.config_entry_id||e.window_key;return e.config_subentry_id?{kind:"subentry",entry_id:t,subentry_id:e.config_subentry_id}:{kind:"entry",entry_id:t}}function ni(e){const t=`/config/integrations/integration/${Me}`;switch(e.kind){case"subentry":case"entry":return`${t}#config_entry=${encodeURIComponent(e.entry_id)}`}}ii.styles=r`
    :host {
      display: inline-flex;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 500;
      white-space: nowrap;
      line-height: 1.4;
    }
    .badge-icon {
      --mdc-icon-size: 14px;
      line-height: 0;
      flex: 0 0 auto;
    }
    button.badge {
      /* Inherit only the family — the font shorthand would reset font-size to
         the page value and make the resumable (manual) badge larger than the
         span badges, which keep the .badge 0.75rem size. */
      font-family: inherit;
      border: none;
      cursor: pointer;
    }
    button.badge:hover {
      filter: brightness(0.92);
    }
    .resume-icon {
      --mdc-icon-size: 14px;
      line-height: 0;
      flex: 0 0 auto;
      opacity: 0.85;
    }
    :host([compact]) .resume-icon {
      --mdc-icon-size: 12px;
    }
    :host([compact]) .badge {
      padding: 1px 6px;
      font-size: 0.7rem;
    }
    :host([compact]) .badge-icon {
      --mdc-icon-size: 12px;
    }
  `,e([ge({attribute:!1})],ii.prototype,"hass",void 0),e([ge()],ii.prototype,"winner",void 0),e([ge({type:Boolean,reflect:!0})],ii.prototype,"compact",void 0),e([ge({type:Boolean,attribute:"integration-enabled"})],ii.prototype,"integrationEnabled",void 0),e([ge({type:Boolean,attribute:"manual-active"})],ii.prototype,"manualActive",void 0),e([ge({attribute:"kind-override"})],ii.prototype,"kindOverride",void 0),e([ge({type:Boolean,reflect:!0})],ii.prototype,"resumable",void 0),ii=e([he("acp-tile-badge")],ii);let ri=class extends ce{constructor(){super(...arguments),this.compact=!1,this.resetEnabled=!0}shouldUpdate(e){if(e.size>1||!e.has("hass"))return!0;const t=e.get("hass"),o=this.discovered?.entities;return fe(t,this.hass,[o?.manual_override_binary,o?.reset_override_button])}_manualActive(){const e=this.discovered.entities.manual_override_binary;return!!e&&"on"===this.hass.states[e]?.state}_manualList(){const e=this.discovered.entities.manual_override_binary;if(!e)return[];const t=this.hass.states[e]?.attributes?.manual_controlled;return Array.isArray(t)?t:[]}_resetManual(){const e=this.discovered.entities.reset_override_button;e&&ti(oi(this.hass,this.discovered.entities.target_position_sensor))&&this.hass.callService("button","press",{entity_id:e})}render(){if(!this.hass||!this.discovered)return Y;const e=this._manualActive(),t=this._manualList(),o=this.discovered.entities.reset_override_button,i=Ve("overrides.reset_manual");return G`
      <div class="wrap">
        <div class="label dim">${Ve("overrides.title")}</div>
        <div class="grid">
          <div class="tile ${e?"active":""}">
            <div class="tile-label">${Ve("overrides.manual")}</div>
            <div class="tile-value">
              ${Ve(e?"overrides.active":"overrides.off")}
            </div>
            ${e&&t.length>0?G`<div class="tile-sub dim">
                  ${Ve("overrides.active_count",{count:t.length})}
                </div>`:Y}
          </div>

          ${o?this.resetEnabled?G`<button class="tile action" @click=${this._resetManual}>
                  <ha-icon icon="mdi:restore"></ha-icon>
                  <div class="tile-value">${i}</div>
                </button>`:G`<button class="tile action readonly" aria-disabled="true" tabindex="-1">
                  <ha-icon icon="mdi:restore"></ha-icon>
                  <div class="tile-value">${i}</div>
                </button>`:Y}
        </div>
      </div>
    `}};ri.styles=r`
    :host {
      display: block;
    }
    .wrap {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .label {
      font-size: 0.78rem;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
      gap: 6px;
    }
    .tile {
      display: flex;
      flex-direction: column;
      gap: 2px;
      padding: 8px 10px;
      border-radius: 6px;
      background: var(--secondary-background-color, rgba(0, 0, 0, 0.04));
      font-size: 0.8rem;
    }
    :host([compact]) .tile {
      padding: 4px 8px;
      font-size: 0.72rem;
    }
    :host([compact]) .tile-sub {
      display: none;
    }
    :host([compact]) .label {
      display: none;
    }
    .tile.active {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .tile.action {
      cursor: pointer;
      border: none;
      text-align: left;
      font-family: inherit;
      align-items: flex-start;
    }
    .tile.action:hover {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .tile.action.readonly {
      cursor: default;
      opacity: 0.85;
      pointer-events: none;
    }
    .tile.action.readonly:hover {
      background: var(--secondary-background-color, rgba(0, 0, 0, 0.04));
      color: inherit;
    }
    .tile-label {
      font-size: 0.72rem;
      opacity: 0.8;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .tile-value {
      font-weight: 500;
    }
    .tile-sub {
      font-size: 0.72rem;
    }
    .dim {
      color: var(--secondary-text-color);
    }
    .tile.active .dim {
      color: inherit;
      opacity: 0.85;
    }
    ha-icon {
      --mdc-icon-size: 18px;
    }
  `,e([ge({attribute:!1})],ri.prototype,"hass",void 0),e([ge({attribute:!1})],ri.prototype,"discovered",void 0),e([ge({type:Boolean,reflect:!0})],ri.prototype,"compact",void 0),e([ge({type:Boolean,attribute:"reset-enabled"})],ri.prototype,"resetEnabled",void 0),ri=e([he("acp-overrides-panel")],ri);let ai=class extends ce{constructor(){super(...arguments),this.compact=!1,this.coverColor=null}shouldUpdate(e){if(e.size>1||!e.has("hass"))return!0;const t=e.get("hass"),o=this.discovered?.entities;return fe(t,this.hass,[o?.target_position_sensor,o?.manual_override_binary,...this.discovered?.managed_covers??[]])}_setPosition(e,t){"cover_tilt"===this.discovered.cover_type?this.hass.callService("cover","set_cover_tilt_position",{entity_id:e,tilt_position:t}):this.hass.callService("cover","set_cover_position",{entity_id:e,position:t})}render(){if(!this.hass||!this.discovered)return Y;const e=co(this.hass,this.discovered),t=ao(this.hass,this.discovered),o=function(e,t){if(!function(e,t){const o=t.entities.manual_override_binary;return!!o&&"on"===e.states[o]?.state}(e,t))return!1;const o=ro(e,t),i=lo(e,t);return null!==o&&null!==i&&Math.round(i)!==Math.round(o)}(this.hass,this.discovered),i=Object.entries(t);return 0===i.length?G`<div class="placeholder">${Ve("covers.placeholder")}</div>`:G`
      <div class="wrap" style=${this.coverColor?`--acp-cover-color:${this.coverColor}`:Y}>
        <div class="head">
          <span class="label">${Ve("covers.title")}</span>
          <span class="targets">
            <span class="target"
              >${Ve(o?"covers.target_solar":"covers.target",{pct:So(e)})}</span
            >
          </span>
        </div>
        ${i.map(([t,i])=>G`
            <div class="cover-group">${this._bar(t,i,e,o)}</div>
          `)}
      </div>
    `}_bar(e,t,o,i){const s=this.hass.states[e]?.attributes?.friendly_name??e,n=t??0,r=o??0;return G`
      <div class="cover">
        <div class="name" ${_t(e)}>${s}</div>
        <div class="num">${So(t)}</div>
        <div
          class="track"
          @click=${t=>this._handleTrackClick(t,e)}
          ${_t(Ve("covers.click_to_set"))}
        >
          <div class="fill" style="width:${n}%"></div>
          <div class="fill-closed" style="width:${100-n}%"></div>
          ${null!==o?G`<div
                class="marker"
                style="left:clamp(1px, ${r}%, calc(100% - 1px))"
                ${_t(Ve(i?"covers.target_tooltip_override":"covers.target_tooltip",{pct:r}))}
              ></div>`:Y}
        </div>
      </div>
    `}_handleTrackClick(e,t){const o=e.currentTarget.getBoundingClientRect(),i=Math.round((e.clientX-o.left)/o.width*100),s=Math.max(0,Math.min(100,i));this._setPosition(t,s)}};var li;ai.styles=r`
    :host {
      display: block;
    }
    .wrap {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .head {
      display: flex;
      justify-content: space-between;
      font-size: 0.78rem;
      color: var(--secondary-text-color);
    }
    .label {
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }
    .targets {
      display: flex;
      gap: 12px;
    }
    .target {
      font-variant-numeric: tabular-nums;
    }
    .cover-group {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .cover {
      display: grid;
      grid-template-columns: minmax(80px, 1fr) 48px 3fr 16px;
      gap: 8px;
      align-items: center;
      font-size: 0.82rem;
    }
    .name {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .name[data-tooltip]:hover {
      cursor: help;
    }
    .name[data-tooltip][acp-tt-shown] {
      cursor: default;
    }
    .track {
      position: relative;
      display: flex;
      height: 10px;
      background: var(--secondary-background-color, rgba(0, 0, 0, 0.08));
      border-radius: 6px;
      cursor: pointer;
      overflow: hidden;
    }
    :host([compact]) .track {
      height: 6px;
    }
    :host([compact]) .cover {
      font-size: 0.75rem;
      gap: 6px;
    }
    :host([compact]) .head {
      display: none;
    }
    .fill {
      height: 100%;
      flex-shrink: 0;
      background: color-mix(in srgb, var(--acp-cover-color, var(--primary-color)) 18%, transparent);
      transition: width 0.3s ease;
    }
    .fill-closed {
      height: 100%;
      flex-shrink: 0;
      background: color-mix(in srgb, var(--acp-cover-color, var(--primary-color)) 50%, transparent);
      transition: width 0.3s ease;
    }
    .marker {
      position: absolute;
      top: -2px;
      width: 2px;
      height: 14px;
      background: var(--accent-color, red);
      transform: translateX(-50%);
      transition: left 0.3s ease;
    }
    .num {
      font-variant-numeric: tabular-nums;
      text-align: right;
    }
    .placeholder {
      color: var(--secondary-text-color);
      text-align: center;
      padding: 16px;
    }
  `,e([ge({attribute:!1})],ai.prototype,"hass",void 0),e([ge({attribute:!1})],ai.prototype,"discovered",void 0),e([ge({type:Boolean,reflect:!0})],ai.prototype,"compact",void 0),e([ge({attribute:!1})],ai.prototype,"coverColor",void 0),ai=e([he("acp-cover-bar")],ai);const ci=864e5;let di=li=class extends ce{constructor(){super(...arguments),this.samples=[],this.events=[],this.now=Date.now(),this._hoverIdx=null,this._onPointerMove=e=>{const t=e.currentTarget.getBoundingClientRect();if(t.width<=0)return;const o=(e.clientX-t.left)/t.width,i=Math.max(0,Math.min(1,o))*li.VIEW_W;this._hoverIdx=this._nearestSampleIdx(i)},this._onPointerLeave=()=>{this._hoverIdx=null}}render(){if(!this.samples||0===this.samples.length)return Y;const{VIEW_W:e,VIEW_H:t,TOP_PAD:o,EVENT_HIT_W:i}=li,s=t-o,n=yo(new Date(this.now)).getTime(),r=t=>rt(t,n,e),a=this.samples.map(e=>{const t=Date.parse(e.t);return{t:t,x:r(t),y:o+(1-hi(e.position)/100)*s,sample:e,inDay:!Number.isNaN(t)&&t>=n&&t<=n+ci}}),l=a.filter(e=>e.inDay).map(e=>`${e.x.toFixed(1)},${e.y.toFixed(1)}`).join(" "),c=(this.events??[]).map(e=>{const s=Date.parse(e.t);if(Number.isNaN(s)||s<n||s>n+ci)return null;const a=r(s),l=`evt-${e.kind}`,c=function(e){const t=`forecast.event.${e.kind}`,o=Ve(t),i=o===t?e.label??e.kind:o,s=Co(e.t);return"—"===s?i:`${i} — ${s}`}(e);return U`<g class="event-group" ${_t(c)}>
          <line
            class="event-hit"
            x1=${a.toFixed(1)}
            x2=${a.toFixed(1)}
            y1=${o}
            y2=${t}
            stroke-width=${i}
          ></line>
          <line
            class="event-marker ${l}"
            x1=${a.toFixed(1)}
            x2=${a.toFixed(1)}
            y1=${o}
            y2=${t}
          ></line>
        </g>`}).filter(e=>null!==e),d=null!==this._hoverIdx&&this._hoverIdx>=0&&this._hoverIdx<a.length?a[this._hoverIdx]:null,h=d?U`<g class="hover-guide" pointer-events="none">
          <line class="hover-line"
            x1=${d.x.toFixed(1)} x2=${d.x.toFixed(1)}
            y1=${o} y2=${t}></line>
          <circle class="hover-dot" cx=${d.x.toFixed(1)} cy=${d.y.toFixed(1)} r="3"></circle>
        </g>`:Y,u=d?G`<div class="hover-label" style=${`left: ${(d.x/e*100).toFixed(2)}%`}>
          ${function(e){const t=Co(e.t),o=`${Math.round(hi(e.position))}%`;return e.handler?`${t} · ${o} · ${e.handler}`:`${t} · ${o}`}(d.sample)}
        </div>`:Y,p=[0,6,12,18,24].map(e=>{const i=r(n+36e5*e);return U`
        <line class="grid faint" x1=${i} y1=${o} x2=${i} y2=${t-.5} />
        <text class="axis-label tick-time" x=${i} y=${t-3} text-anchor="middle">${e.toString().padStart(2,"0")}:00</text>
      `}),g=this.now,m=r(g),f=g>=n&&g<=n+ci?U`<g class="now-group" ${_t(Co(new Date(g).toISOString()))}>
          <line class="now-hit" x1=${m.toFixed(1)} y1=${o} x2=${m.toFixed(1)} y2=${t-.5}></line>
          <line class="now" x1=${m.toFixed(1)} y1=${o} x2=${m.toFixed(1)} y2=${t-.5}></line>
        </g>`:Y;return G`
      <div class="wrap">
        <svg
          viewBox="0 0 ${e} ${t}"
          preserveAspectRatio="none"
          xmlns="http://www.w3.org/2000/svg"
          @pointermove=${this._onPointerMove}
          @pointerleave=${this._onPointerLeave}
        >
          <line class="baseline" x1="0" y1=${t-.5} x2=${e} y2=${t-.5}></line>
          <text class="axis-label" x="4" y=${o+8} text-anchor="start">100%</text>
          ${p}
          <polyline class="curve" points=${l} fill="none"></polyline>
          ${c} ${h} ${f}
        </svg>
        ${u}
      </div>
    `}_nearestSampleIdx(e){const t=yo(new Date(this.now)).getTime();let o=-1,i=Number.POSITIVE_INFINITY;for(let s=0;s<this.samples.length;s++){const n=Date.parse(this.samples[s].t);if(Number.isNaN(n)||n<t||n>t+ci)continue;const r=rt(n,t,li.VIEW_W),a=Math.abs(r-e);a<i&&(i=a,o=s)}return o>=0?o:null}};function hi(e){return Number.isNaN(e)||e<0?0:e>100?100:e}di.VIEW_W=600,di.VIEW_H=80,di.TOP_PAD=10,di.EVENT_HIT_W=12,di.styles=r`
    :host {
      display: block;
    }
    .wrap {
      position: relative;
      width: 100%;
    }
    svg {
      display: block;
      width: 100%;
      height: 80px;
      overflow: visible;
    }
    .baseline {
      stroke: var(--divider-color, rgba(0, 0, 0, 0.12));
      stroke-width: 1;
    }
    .curve {
      stroke: var(--primary-color);
      stroke-width: 1.5;
      vector-effect: non-scaling-stroke;
    }
    /* Floating-tooltip cursor lifecycle: a help cursor hints at the event
       marker on hover, flipping to default once OUR bubble appears. */
    [data-tooltip]:hover {
      cursor: help;
    }
    [data-tooltip][acp-tt-shown] {
      cursor: default;
    }
    .event-hit {
      stroke: transparent;
      vector-effect: non-scaling-stroke;
    }
    .event-marker {
      stroke: var(--secondary-text-color);
      stroke-width: 1;
      stroke-dasharray: 2 2;
      vector-effect: non-scaling-stroke;
      pointer-events: none;
    }
    .evt-sunrise {
      stroke: #fbc02d;
    }
    .evt-sunset {
      stroke: #f57c00;
    }
    .evt-fov_enter {
      stroke: #4caf50;
    }
    .evt-fov_exit {
      stroke: #9e9e9e;
    }
    .hover-line {
      stroke: var(--primary-text-color, currentColor);
      stroke-width: 1;
      stroke-dasharray: 1 2;
      opacity: 0.55;
      vector-effect: non-scaling-stroke;
    }
    .hover-dot {
      fill: var(--primary-color);
      stroke: var(--card-background-color, #fff);
      stroke-width: 1;
    }
    .hover-label {
      position: absolute;
      bottom: calc(100% + 4px);
      transform: translateX(-50%);
      padding: 2px 6px;
      border-radius: 4px;
      background: var(--secondary-background-color, rgba(0, 0, 0, 0.75));
      color: var(--primary-text-color, #fff);
      font-size: 0.72rem;
      white-space: nowrap;
      pointer-events: none;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
    }
    .axis-label {
      font-size: 9px;
      fill: var(--secondary-text-color, #888);
      pointer-events: none;
      vector-effect: non-scaling-stroke;
      user-select: none;
    }
    .grid {
      stroke: var(--divider-color);
      stroke-width: 0.5;
      opacity: 0.6;
    }
    .grid.faint {
      opacity: 0.25;
    }
    .now {
      stroke: var(--accent-color, crimson);
      stroke-width: 1.25;
      pointer-events: none;
    }
    .now-hit {
      stroke: transparent;
      stroke-width: 10;
    }
  `,e([ge({attribute:!1})],di.prototype,"hass",void 0),e([ge({attribute:!1})],di.prototype,"samples",void 0),e([ge({attribute:!1})],di.prototype,"events",void 0),e([ge({attribute:!1})],di.prototype,"now",void 0),e([me()],di.prototype,"_hoverIdx",void 0),di=li=e([he("acp-forecast-strip")],di);let ui=class extends ce{constructor(){super(...arguments),this.open=!1,this.advancedOpen=!1,this.showCompass=!0,this.showElevationChart=!0,this._cancelMinuteTimer=null,this._listSource=null,this._list=[],this._onResume=()=>{const e=this.discovered.entities.reset_override_button;e&&ti(this._target())&&this.hass.callService("button","press",{entity_id:e})},this._toggleAdvanced=()=>{this.advancedOpen=!this.advancedOpen},this._openDevicePage=()=>{const e=this.discovered.device_id;e&&this._navigate(`/config/devices/device/${e}`)},this._openWindowSettings=()=>{this._navigate(ni(si(this.discovered)))},this._onBackdrop=e=>{e.target===e.currentTarget&&this._emitClose()},this._emitClose=()=>{this.dispatchEvent(new CustomEvent("acp-dialog-close",{bubbles:!0,composed:!0}))},this._stop=e=>{e.stopPropagation()}}updated(){this._syncMinuteTimer(this.open)}disconnectedCallback(){super.disconnectedCallback(),this._syncMinuteTimer(!1)}_syncMinuteTimer(e){e&&null===this._cancelMinuteTimer?this._cancelMinuteTimer=Po(()=>this.requestUpdate()):e||null===this._cancelMinuteTimer||(this._cancelMinuteTimer(),this._cancelMinuteTimer=null)}get _discoveredList(){return this.discovered!==this._listSource&&(this._listSource=this.discovered,this._list=this.discovered?[this.discovered]:[]),this._list}_buildHandlerLabels(){const e={};for(const[t,o]of Object.entries(Ie))e[t]=Ve(o);return e}render(){if(!this.open||!this.hass||!this.discovered)return Y;const e=oo(this.hass,this.discovered),t=io(this.hass,this.discovered),o=this._target(),i=t?Go(t.trace,t,e,this._buildHandlerLabels(),o):"",s=this._shouldShowResume(),n=this._switchOn("automatic_control_switch"),r=this._badgeKinds(e,n),a=Ve("dialog.window_settings"),l=Ve("dialog.open_device_page"),c=Ve("dialog.close");return G`
      <div class="backdrop" data-open @click=${this._onBackdrop}>
        <div class="dialog" @click=${this._stop} role="dialog" aria-modal="true">
          <div class="header">
            <ha-icon
              class="cover-icon"
              icon=${Te[this.discovered.cover_type]??"mdi:window-shutter"}
            ></ha-icon>
            <div class="title">${this.discovered.entry_title}</div>
            <div class="badges">
              ${r.map(t=>G`<acp-tile-badge
                    .hass=${this.hass}
                    .winner=${e}
                    .kindOverride=${t}
                    .integrationEnabled=${n}
                  ></acp-tile-badge>`)}
            </div>
            <button
              class="icon-btn options-link"
              type="button"
              aria-label=${a}
              ${_t(a)}
              @click=${this._openWindowSettings}
            >
              <ha-icon icon="mdi:tune-variant"></ha-icon>
            </button>
            ${this.discovered.device_id?G`<button
                  class="icon-btn device-link"
                  type="button"
                  aria-label=${l}
                  ${_t(l)}
                  @click=${this._openDevicePage}
                >
                  <ha-icon icon="mdi:cog"></ha-icon>
                </button>`:Y}
            <button class="close" type="button" aria-label=${c} @click=${this._emitClose}>
              ✕
            </button>
          </div>

          ${i?G`<div class="summary">${i}</div>`:Y}

          <div class="position-block">
            <div class="position-label">${Ve("dialog.target")}</div>
            <div class="position-value">${So(o)}</div>
          </div>

          <acp-cover-bar .hass=${this.hass} .discovered=${this.discovered}></acp-cover-bar>

          ${this._renderForecastStrip()} ${this._renderControls()}
          ${s?G`<div class="actions">
                <button class="resume" type="button" @click=${this._onResume}>
                  ${Ve("dialog.resume_auto")}
                </button>
              </div>`:Y}

          <button class="advanced-toggle" type="button" @click=${this._toggleAdvanced}>
            ${this.advancedOpen?Ve("dialog.hide_advanced"):Ve("dialog.show_advanced")}
          </button>
          ${this.advancedOpen?G`<div class="advanced">
                ${this.showCompass?G`<div class="advanced-compass">
                      <acp-sky-compass
                        .hass=${this.hass}
                        .discovered_list=${this._discoveredList}
                        ?compact=${!0}
                        .showLegend=${!1}
                        .showStats=${!0}
                      ></acp-sky-compass>
                    </div>`:Y}
                ${this.showElevationChart?G`<acp-elevation-chart
                      .hass=${this.hass}
                      .discoveredList=${this._discoveredList}
                      ?compact=${!0}
                    ></acp-elevation-chart>`:Y}
                <acp-decision-strip
                  .hass=${this.hass}
                  .discovered=${this.discovered}
                ></acp-decision-strip>
                ${this._renderMoves()}
                <acp-overrides-panel
                  .hass=${this.hass}
                  .discovered=${this.discovered}
                ></acp-overrides-panel>
              </div>`:Y}
        </div>
      </div>
    `}_badgeKinds(e,t){io(this.hass,this.discovered);const o=Zo({winner:e,integrationEnabled:t,manualActive:this._manualOverrideOn()}),i=ei(0,e);return Jo([o],this.badges,i)}_target(){const e=this.discovered.entities.target_position_sensor;if(!e)return null;const t=this.hass.states[e];if(!t)return null;const o=parseFloat(t.state);return Number.isNaN(o)?null:o}_manualOverrideOn(){const e=this.discovered.entities.manual_override_binary;return!!e&&"on"===this.hass.states[e]?.state}_switchOn(e){const t=this.discovered.entities[e];return!t||"off"!==this.hass.states[t]?.state}_shouldShowResume(){return!!this.discovered.entities.reset_override_button&&this._manualOverrideOn()}_renderControls(){const e=[{role:"automatic_control_switch",label:Ve("dialog.automatic")},{role:"climate_mode_switch",label:Ve("dialog.climate")},{role:"manual_toggle_switch",label:Ve("dialog.manual_detection")}].filter(e=>!!this.discovered.entities[e.role]);return 0===e.length?Y:G`<div class="controls-block">
      <div class="controls-label">${Ve("dialog.controls")}</div>
      <div class="controls-row">${e.map(e=>this._renderSwitchChip(e.role,e.label))}</div>
    </div>`}_renderSwitchChip(e,t){const o=this.discovered.entities[e],i="on"===this.hass.states[o]?.state,s=Ve(i?"dialog.state_on":"dialog.state_off"),n=Ve(i?"dialog.on":"dialog.off");return G`<button
      class="ctrl-toggle ${i?"on":"off"}"
      type="button"
      aria-pressed=${i}
      aria-label=${Ve("dialog.toggle_hint",{label:t,state:s})}
      @click=${()=>this._toggleSwitch(o,i)}
    >
      <span class="ctrl-label">${t}</span>
      <span class="ctrl-state">${n}</span>
    </button>`}_toggleSwitch(e,t){this.hass.callService("switch",t?"turn_off":"turn_on",{entity_id:e})}_renderForecastStrip(){const e=function(e,t){const o=to(e,t),i=o?.forecast_today;if(!Array.isArray(i)||0===i.length)return null;const s=[],n=[];let r=null;for(const e of i)e&&"string"==typeof e.time&&(null!==r&&(s.push({t:e.time,position:r.position,handler:r.intent}),e.intent!==r.intent&&n.push({t:e.time,kind:e.intent,label:e.intent})),s.push({t:e.time,position:e.position,handler:e.intent}),r=e);if(null!==r){const e=Date.parse(r.time);if(!Number.isNaN(e)){const t=new Date(e);t.setHours(23,59,59,0),t.getTime()-e<864e5&&s.push({t:t.toISOString(),position:r.position,handler:r.intent})}}return{forecast:s,events:n}}(this.hass,this.discovered);return e&&0!==e.forecast.length?G`<div class="forecast-block">
      <div class="forecast-label">${Ve("dialog.todays_forecast")}</div>
      <acp-forecast-strip
        .hass=${this.hass}
        .samples=${e.forecast}
        .events=${e.events}
        .now=${Date.now()}
      ></acp-forecast-strip>
      <div class="forecast-note">${Ve("forecast.solar_only_note")}</div>
    </div>`:Y}_renderMoves(){const e=to(this.hass,this.discovered),t=Object.entries(e?.last_moves??{}),o=Object.entries(e?.move_blocked_by??{});if(0===t.length&&0===o.length)return Y;const i=e=>this.hass.states[e]?.attributes?.friendly_name??e;return G`<div class="moves-section">
      <div class="moves-label">${Ve("dialog.last_moves")}</div>
      ${t.map(([e,t])=>G`<div class="move-row">
            <span class="move-name" ${_t(e)}>${i(e)}</span>
            <span class="move-line dim">${t}</span>
          </div>`)}
      ${o.map(([e,t])=>G`<div class="move-row blocked">
            <span class="move-name" ${_t(e)}>${i(e)}</span>
            <span class="move-line">${Ve("dialog.move_blocked",{gate:t})}</span>
          </div>`)}
    </div>`}_navigate(e){history.pushState(null,"",e),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}})),this._emitClose()}};function pi(){return G`
    <div
      class="editor-footer"
      style="display:flex;align-items:center;justify-content:flex-end;gap:8px;"
    >
      <span class="version-footer dim">
        ${Ve("root.footer_version",{version:_e})}
      </span>
    </div>
  `}ui.styles=r`
    :host {
      display: contents;
    }
    .backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.5);
      z-index: 9999;
      display: flex;
      align-items: flex-start;
      justify-content: center;
      padding: 5vh 12px;
      overflow-y: auto;
    }
    .dialog {
      width: 100%;
      max-width: 520px;
      background: var(--card-background-color, white);
      color: var(--primary-text-color);
      border-radius: 12px;
      padding: 14px 16px 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      box-shadow: 0 12px 36px rgba(0, 0, 0, 0.35);
    }
    .header {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .header .cover-icon {
      --mdc-icon-size: 22px;
    }
    .header .title {
      font-size: 1.1rem;
      font-weight: 600;
      flex: 1;
      min-width: 0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .header .badges {
      display: inline-flex;
      gap: 4px;
      flex-wrap: wrap;
    }
    .close {
      border: 0;
      background: transparent;
      cursor: pointer;
      font-size: 1.1rem;
      color: var(--secondary-text-color);
      padding: 4px 6px;
    }
    .close:hover {
      color: var(--primary-text-color);
    }
    .icon-btn {
      border: 0;
      background: transparent;
      cursor: pointer;
      color: var(--secondary-text-color);
      padding: 4px 6px;
      display: inline-flex;
      align-items: center;
      --mdc-icon-size: 18px;
    }
    .icon-btn:hover {
      color: var(--primary-text-color);
    }
    .summary {
      font-size: 0.9rem;
      font-style: italic;
      color: var(--secondary-text-color);
    }
    .position-block {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.95rem;
    }
    .position-label {
      color: var(--secondary-text-color);
    }
    .position-value {
      font-variant-numeric: tabular-nums;
      font-weight: 600;
    }
    .actions {
      display: flex;
      gap: 8px;
    }
    .resume {
      padding: 6px 14px;
      border: 1px solid var(--primary-color);
      border-radius: 999px;
      background: transparent;
      color: var(--primary-color);
      font-size: 0.9rem;
      cursor: pointer;
    }
    .resume:hover {
      background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.08);
    }
    .advanced-toggle {
      border: 0;
      background: transparent;
      cursor: pointer;
      color: var(--primary-color);
      font-size: 0.85rem;
      text-align: left;
      padding: 4px 0;
    }
    .advanced {
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding-top: 4px;
      border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.08));
    }
    .advanced-compass {
      display: flex;
      justify-content: center;
    }
    .moves-section {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .moves-label {
      font-size: 0.78rem;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .move-row {
      display: grid;
      grid-template-columns: minmax(80px, 1fr) auto;
      gap: 8px;
      align-items: baseline;
      font-size: 0.82rem;
      padding: 1px 4px;
    }
    .move-name {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .move-line {
      font-variant-numeric: tabular-nums;
      text-align: right;
    }
    .move-row.blocked .move-line {
      color: var(--warning-color, orange);
    }
    .move-name[data-tooltip]:hover {
      cursor: help;
    }
    .move-name[data-tooltip][acp-tt-shown] {
      cursor: default;
    }
    .forecast-block {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .forecast-label {
      font-size: 0.78rem;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .forecast-note {
      font-size: 0.7rem;
      color: var(--secondary-text-color);
      opacity: 0.75;
    }
    .controls-block {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .controls-label {
      font-size: 0.78rem;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .controls-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .ctrl-toggle {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 12px;
      border-radius: 999px;
      border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.16));
      background: transparent;
      cursor: pointer;
      font-size: 0.8rem;
      color: var(--primary-text-color);
    }
    .ctrl-toggle .ctrl-label {
      font-weight: 500;
    }
    .ctrl-toggle .ctrl-state {
      font-size: 0.75rem;
      color: var(--secondary-text-color);
    }
    .ctrl-toggle.on {
      background: rgba(76, 175, 80, 0.16);
      border-color: rgba(76, 175, 80, 0.5);
    }
    .ctrl-toggle.on .ctrl-state {
      color: #1b5e20;
    }
    .ctrl-toggle.off {
      opacity: 0.85;
    }
    .ctrl-toggle:hover {
      background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.08);
    }
  `,e([ge({attribute:!1})],ui.prototype,"hass",void 0),e([ge({attribute:!1})],ui.prototype,"discovered",void 0),e([ge({type:Boolean,reflect:!0})],ui.prototype,"open",void 0),e([ge({type:Boolean})],ui.prototype,"advancedOpen",void 0),e([ge({type:Boolean})],ui.prototype,"showCompass",void 0),e([ge({type:Boolean})],ui.prototype,"showElevationChart",void 0),e([ge({attribute:!1})],ui.prototype,"badges",void 0),ui=e([he("acp-more-info-dialog")],ui);const gi=["auto","solar","manual","climate","glare_zone","privacy","sunset"],mi={show_position:!0,show_state:!0,show_decision_summary:!1,show_controls:!0,show_badge:!0,show_compass:!0,show_elevation_chart:!0,layout:"detailed",badge_auto:!0,badge_solar:!0,badge_manual:!0,badge_climate:!0,badge_glare_zone:!0,badge_privacy:!0,badge_sunset:!0},fi={window:"editor.common.window",name:"editor.tile.name",icon:"editor.tile.icon",cover:"editor.tile.cover",layout:"editor.tile.layout",show_position:"editor.tile.show_position",show_state:"editor.tile.show_state",show_decision_summary:"editor.tile.show_decision_summary",show_controls:"editor.tile.show_controls",show_badge:"editor.tile.show_badge",badge_section:"editor.tile.badge_section",badge_auto:"editor.tile.badge_auto",badge_solar:"editor.tile.badge_solar",badge_manual:"editor.tile.badge_manual",badge_climate:"editor.tile.badge_climate",badge_glare_zone:"editor.tile.badge_glare_zone",badge_privacy:"editor.tile.badge_privacy",badge_sunset:"editor.tile.badge_sunset",show_compass:"editor.tile.show_compass",show_elevation_chart:"editor.tile.show_elevation_chart",tap_action:"editor.tile.tap_action",hold_action:"editor.tile.hold_action",double_tap_action:"editor.tile.double_tap_action"};let _i=class extends ce{constructor(){super(...arguments),this._windows=null,this._windowsError=null,this._registry=null,this._managedCovers=[],this._windowsFetchInFlight=!1,this._registryFetchInFlight=!1,this._unsubRegistry=null,this._computeLabel=e=>{const t=fi[e.name];return t?Ve(t):e.name},this._valueChanged=e=>{e.stopPropagation();const t={...e.detail.value};for(const[e,o]of Object.entries(mi))e.startsWith("badge_")?t[e]===o&&delete t[e]:this._config&&Object.prototype.hasOwnProperty.call(this._config,e)||t[e]!==o||delete t[e];const o={};for(const e of gi){const i=`badge_${e}`;!1===t[i]&&(o[e]=!1),delete t[i]}const i=t.window;delete t.window;let s={...this._config??{type:""},...t};"string"==typeof i&&i&&i!==kt(this._config)&&(s=$t(s,i)),Object.keys(o).length>0?s.badges=o:delete s.badges,this._emit(s)}}setConfig(e){this._config={...e}}disconnectedCallback(){super.disconnectedCallback(),this._unsubRegistry&&(this._unsubRegistry(),this._unsubRegistry=null)}updated(e){e.has("hass")&&this.hass&&(this._ensureWindows(),this._ensureRegistry()),e.has("_registry")&&null!==this._registry&&this._maybePrefillCover()}_ensureWindows(){this._windows||this._windowsFetchInFlight||(this._windowsFetchInFlight=!0,Qt(this.hass).then(e=>{this._windows=e,this._windowsError=null,this._hasBinding()||1!==e.length||this._emit($t(this._config??{type:""},e[0].window_key)),this._maybePrefillCover()}).catch(e=>{this._windowsError=e?.message??"failed to load windows"}).finally(()=>{this._windowsFetchInFlight=!1}))}_hasBinding(){return!!(this._config?.window||this._config?.entry_id||this._config?.cover)}_ensureRegistry(){null!==this._registry||this._registryFetchInFlight||(this._registryFetchInFlight=!0,Wt(this.hass).then(e=>{this._registry=e,this._maybePrefillCover()}).catch(()=>{this._registry=[]}).finally(()=>{this._registryFetchInFlight=!1})),this._unsubRegistry||(this._unsubRegistry=Vt(this.hass,()=>{this._registryFetchInFlight=!0,Wt(this.hass).then(e=>{this._registry=e}).catch(()=>{}).finally(()=>{this._registryFetchInFlight=!1})}))}_emit(e){this._config=e,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e},bubbles:!0,composed:!0}))}_maybePrefillCover(){const e=this._config;if(!e||!kt(e)||e.cover||!this._registry||!this.hass)return;const t=Dt(this.hass,e,this._registry);this._managedCovers=t?.managed_covers??[],1===t?.managed_covers.length&&this._emit({...e,cover:t.managed_covers[0]})}render(){if(!this._config)return Y;if(this._windowsError&&!this._windows)return G`
        <div class="form">
          <div class="error">${Ve("editor.common.load_failed",{error:this._windowsError})}</div>
          <label class="field-label" for="entry-id-fallback"
            >${Ve("editor.common.window_fallback_label")}</label
          >
          <input
            id="entry-id-fallback"
            type="text"
            class="text-input"
            .value=${kt(this._config)}
            placeholder=${Ve("editor.common.window_manual_placeholder")}
            @change=${e=>this._emit($t(this._config??{type:""},e.target.value))}
          />
          ${pi()}
        </div>
      `;const e=this._schema(),{badges:t,entry_id:o,...i}=this._config,s={};for(const e of gi)t&&!1===t[e]&&(s[`badge_${e}`]=!1);const n=kt(this._config),r={...mi,...i,...s,...n?{window:n}:{}};return G`
      <div class="form">
        <ha-form
          .hass=${this.hass}
          .data=${r}
          .schema=${e}
          .computeLabel=${this._computeLabel}
          @value-changed=${this._valueChanged}
        ></ha-form>
        ${this._managedCovers.length>1&&!this._config?.cover?G`<div class="hint">${Ve("editor.tile.cover_blank_hint")}</div>`:Y}
        ${pi()}
      </div>
    `}_schema(){const e=this._windowOptions(),t=[{value:"one-line",label:Ve("editor.tile.layout_option_one_line")},{value:"detailed",label:Ve("editor.tile.layout_option_detailed")}];let o={entity:{domain:"cover"}};if(this._registry&&kt(this._config)){const e=Dt(this.hass,this._config,this._registry);e&&e.managed_covers.length>0&&(o={entity:{domain:"cover",include_entities:e.managed_covers}})}return[{name:"window",required:!this._config?.cover,selector:{select:{options:e,mode:"dropdown"}}},{name:"name",selector:{text:{}}},{name:"icon",selector:{icon:{}}},{name:"cover",selector:o},{name:"layout",selector:{select:{mode:"list",options:t}}},{name:"show_position",selector:{boolean:{}}},{name:"show_state",selector:{boolean:{}}},{name:"show_decision_summary",selector:{boolean:{}}},{name:"show_controls",selector:{boolean:{}}},{name:"show_badge",selector:{boolean:{}}},{type:"expandable",name:"",title:Ve("editor.tile.badge_section"),icon:"mdi:label-multiple-outline",schema:[{type:"grid",name:"",schema:gi.map(e=>({name:`badge_${e}`,selector:{boolean:{}}}))}]},{name:"show_compass",selector:{boolean:{}}},{name:"show_elevation_chart",selector:{boolean:{}}},{name:"tap_action",selector:{ui_action:{}}},{name:"hold_action",selector:{ui_action:{}}},{name:"double_tap_action",selector:{ui_action:{}}}]}_windowOptions(){const e=(this._windows??[]).map(e=>({value:e.window_key,label:e.title})),t=kt(this._config);return t&&!e.some(e=>e.value===t)&&e.unshift({value:t,label:Ve("editor.common.unknown_entry",{entry:t})}),e}};_i.styles=r`
    :host {
      display: block;
    }
    .form {
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding: 8px 0;
    }
    .field-label {
      font-weight: 500;
      font-size: 0.88rem;
      color: var(--primary-text-color);
    }
    .text-input {
      width: 100%;
      padding: 8px 10px;
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      background: var(--card-background-color, transparent);
      color: var(--primary-text-color);
      font-size: 0.9rem;
      font-family: inherit;
    }
    .error {
      font-size: 0.82rem;
      color: var(--error-color, crimson);
    }
    .hint {
      font-size: 0.8rem;
      color: var(--secondary-text-color, #888);
      padding: 4px 0 0;
    }
    .version-footer {
      font-size: 0.7rem;
      text-align: right;
    }
    .dim {
      color: var(--secondary-text-color);
    }
  `,e([ge({attribute:!1})],_i.prototype,"hass",void 0),e([me()],_i.prototype,"_config",void 0),e([me()],_i.prototype,"_windows",void 0),e([me()],_i.prototype,"_windowsError",void 0),e([me()],_i.prototype,"_registry",void 0),e([me()],_i.prototype,"_managedCovers",void 0),_i=e([he($e)],_i);let vi=class extends ce{constructor(){super(...arguments),this._registry=null,this._registryError=null,this._dialogOpen=!1,this._unsubRegistry=null,this._fetchInFlight=!1,this._memo=Bt(),this._discovered=null,this._fetchGen=0,this._closeDialog=()=>{this._dialogOpen=!1},this._holdTimer=null,this._pendingTapTimer=null,this._holdFired=!1,this._onPointerDown=()=>{this._holdFired=!1,null!=this._holdTimer&&clearTimeout(this._holdTimer),Xo(this._config?.hold_action)&&(this._holdTimer=setTimeout(()=>{this._holdFired=!0,this._holdTimer=null,this._fireAction("hold")},500))},this._onPointerUp=()=>{null!=this._holdTimer&&(clearTimeout(this._holdTimer),this._holdTimer=null)},this._onPointerCancel=()=>{null!=this._holdTimer&&(clearTimeout(this._holdTimer),this._holdTimer=null)},this._onClick=()=>{if(!this._holdFired)return Xo(this._config?.double_tap_action)?null!=this._pendingTapTimer?(clearTimeout(this._pendingTapTimer),this._pendingTapTimer=null,void this._fireAction("double_tap")):void(this._pendingTapTimer=setTimeout(()=>{this._pendingTapTimer=null,this._fireAction("tap")},250)):void this._fireAction("tap");this._holdFired=!1}}setConfig(e){const t=yt(e);if(!t)throw new Error(`${xe}: set \`window\` (window key) or \`cover\` (cover entity); a legacy \`entry_id\` also works. It must be a non-empty string.`);let o={...e};if("string"==typeof o.tap_action&&(o={...o,tap_action:"none"===o.tap_action?{action:"none"}:void 0}),this._config=o,o.tooltips&&gt(o.tooltips),null===this._registry){const e=Xt.get(bt(t));e&&(this._registry=e.entries)}}getCardSize(){return 1}getGridOptions(){return{columns:"full",rows:"auto",min_columns:3,min_rows:"one-line"!==this._config?.layout?2:1}}static async getStubConfig(e){let t="";try{const o=await Qt(e);t=o[0]?.window_key??""}catch{}return{type:`custom:${xe}`,window:t}}static async getConfigElement(){return document.createElement($e)}connectedCallback(){if(super.connectedCallback(),null===this._registry){const e=Lt();e&&(this._registry=e)}this.hass&&this._ensureRegistry()}disconnectedCallback(){super.disconnectedCallback(),this._unsubRegistry&&(this._unsubRegistry(),this._unsubRegistry=null)}updated(e){e.has("hass")&&this.hass&&this._ensureRegistry()}shouldUpdate(e){return e.size>1||!e.has("hass")||(!this._discovered||fe(e.get("hass"),this.hass,[...Object.values(this._discovered.entities),...this._discovered.managed_covers]))}willUpdate(e){this._config&&this.hass&&null!==this._registry&&(e.has("hass")||e.has("_registry")||e.has("_config"))&&(this._discovered=this._memo(this.hass,this._config,this._registry))}_ensureRegistry(){this._fetchRegistry(),this._unsubRegistry||(this._unsubRegistry=Vt(this.hass,()=>{this._fetchRegistry(!0)}))}_fetchRegistry(e=!1){if(this._fetchInFlight)return;this._fetchInFlight=!0;const t=++this._fetchGen;Yt(this.hass,e).then(e=>{if(t!==this._fetchGen)return;if(e===this._registry)return;this._registry=e,this._registryError=null;const o=yt(this._config);o&&this.hass&&Xt.set(bt(o),Kt(this.hass,o,e))}).catch(e=>{t===this._fetchGen&&(this._registryError=e?.message??"entity registry fetch failed")}).finally(()=>{t===this._fetchGen&&(this._fetchInFlight=!1)})}render(){if(!this._config||!this.hass)return Y;if(null===this._registry)return G`<ha-card>
        <div class="empty">
          <p class="dim">
            ${this._registryError?Ve("tile.registry_failed",{error:this._registryError}):Ve("tile.loading")}
          </p>
        </div>
      </ha-card>`;const e=this._discovered;return e?G`
      <ha-card>${this._renderTile(e)}</ha-card>
      <acp-more-info-dialog
        .hass=${this.hass}
        .discovered=${e}
        .open=${this._dialogOpen}
        .showCompass=${!1!==this._config.show_compass}
        .showElevationChart=${!1!==this._config.show_elevation_chart}
        .badges=${this._config.badges}
        @acp-dialog-close=${this._closeDialog}
      ></acp-more-info-dialog>
    `:G`<ha-card>
        <div class="empty">
          <p class="dim">
            ${Ve("tile.entry_not_found",{entry:this._notFoundLabel()})}
          </p>
        </div>
      </ha-card>`}_buildHandlerLabels(){const e={};for(const[t,o]of Object.entries(Ie))e[t]=Ve(o);return e}_renderTile(e){const t=this._config,o=t.name??e.entry_title,i=this._targetCovers(e),s=i[0],n=this._liveCoverPosition(e,s),r=t.icon??function(e,t){if(null!==t&&!Number.isNaN(t)){if(t>=95)return Fe[e]??"mdi:window-shutter-open";if(t<=5)return Re[e]??"mdi:window-shutter"}return Te[e]??"mdi:window-shutter"}(e.cover_type,n),a=!1!==t.show_position,l=!1!==t.show_state,c=!1!==t.show_controls,d=!1!==t.show_badge,h="one-line"!==t.layout,u=this._currentPosition(e),p=n??u,g=null!==n&&n>=100,m=null!==n&&n<=0,f=oo(this.hass,e),_=io(this.hass,e),v=this._isFullyInert(t),y=!0===t.show_decision_summary&&_?Go(_.trace,_,f,this._buildHandlerLabels(),u):"",w=!!y&&h,b=this._switchOn(e,"automatic_control_switch"),x=this._manualOverrideOn(e),$=function(e){const t=Zo(e);return!1===e.inTimeWindow&&!1!==e.badges?.off_schedule&&"off"!==t&&"manual"!==t?"off_schedule":t}({winner:f,integrationEnabled:b,manualActive:x,badges:t.badges}),k=ei(0,f),S=null!==$&&Jo([$],t.badges,k).length>0,A=d&&S,C=!!(E={integrationEnabled:b,automaticControl:b,manualActive:x}).integrationEnabled&&!!E.automaticControl&&!E.manualActive;var E;const M=h&&d&&!1!==t.badges?.auto&&C,z=!(M&&"auto"===$),O=l&&s?function(e,t){if(!e||!t)return null;const o=e.states[t];if(!o?.state||"unknown"===o.state||"unavailable"===o.state)return null;if("function"==typeof e.formatEntityState){const t=e.formatEntityState(o);if(t)return t}if("function"==typeof e.localize){const t=e.localize(`component.cover.entity_component._.state.${o.state}`);if(t)return t}return o.state.charAt(0).toUpperCase()+o.state.slice(1)}(this.hass,s):null,I=[O,a&&null!==p?So(p):null].filter(e=>!!e),T=!!O,F=x&&!!e.entities.reset_override_button,R=!1===t.show_battery?null:function(e,t){if(!e||!t)return null;const o=e.find(e=>e.entity_id===t);if(!o?.device_id)return null;const i=e.find(e=>e.device_id===o.device_id&&e.entity_id.startsWith("sensor.")&&/(^|_)battery(_|$)/.test(e.entity_id.split(".")[1]));return i?.entity_id??null}(this._registry,s),j=function(e,t){if(!t)return null;const o=e.states[t];if(!o||"unavailable"===o.state||"unknown"===o.state)return{level:null,available:!1};const i=parseFloat(o.state);return Number.isNaN(i)?{level:null,available:!1}:{level:i,available:!0}}(this.hass,R);let N=Y;if(null!==j){const e=j.available?j.level<=12?" low":j.level<=25?" warn":"":" low",t=j.available?j.level<=25?"mdi:battery-alert":"mdi:battery-outline":"mdi:battery-unknown",o=j.available?j.level<=40?`${Math.round(j.level)}%`:"":"?";N=G`<span class=${`battery${e}`} title=${Ve("tile.battery")}
        ><ha-icon icon=${t}></ha-icon>${o}</span
      >`}const P=I.length>0||null!==j?G`<div class="position">
            ${I.length>0?G`<span class="pos-text">${I.join(" · ")}</span>`:Y}${N}
          </div>`:Y,D=A?G`<acp-tile-badge
          .hass=${this.hass}
          .winner=${f}
          .kindOverride=${$??void 0}
          .integrationEnabled=${b}
          .manualActive=${x}
          .resumable=${F}
          @acp-resume=${()=>this._resume(e)}
        ></acp-tile-badge>`:Y,K=M?G`<acp-tile-badge
          .hass=${this.hass}
          .winner=${f}
          .kindOverride=${"auto"}
          .integrationEnabled=${b}
        ></acp-tile-badge>`:Y;return G`
      <div
        class=${`tile-body${h?" detailed":""}${w?" has-summary":""}${T?" has-state-label":""}`}
        role=${v?"group":"button"}
        tabindex=${v?-1:0}
        @pointerdown=${this._onPointerDown}
        @pointerup=${this._onPointerUp}
        @pointercancel=${this._onPointerCancel}
        @pointerleave=${this._onPointerCancel}
        @click=${this._onClick}
      >
        <div class="cover-icon-wrap">
          <ha-icon class="cover-icon" icon=${r}></ha-icon>
        </div>
        <div class="label">
          <div class="title">${o}</div>
          ${y&&!h?G`<div class="summary">${y}</div>`:Y}
          ${w?G`<div class="summary inline-summary" ${_t(y)}>${y}</div>`:Y}
        </div>
        ${h&&M?G`<div class="auto-line">${K}</div>`:Y}
        ${h?G`<div class="detail-line">
              ${P}${z?D:Y}
            </div>`:G`${P}`}
        ${c?G`<div class="controls" @click=${this._stop} @pointerdown=${this._stop}>
              <button
                class="up"
                type="button"
                aria-label=${Ve("tile.open")}
                ?disabled=${0===i.length||g}
                @click=${()=>this._setCoversPosition(e,i,100)}
              >
                <ha-icon icon="mdi:arrow-up"></ha-icon>
              </button>
              <button
                class="stop"
                type="button"
                aria-label=${Ve("tile.stop")}
                ?disabled=${0===i.length}
                @click=${()=>this._stopCovers(i)}
              >
                <ha-icon icon="mdi:stop"></ha-icon>
              </button>
              <button
                class="down"
                type="button"
                aria-label=${Ve("tile.close")}
                ?disabled=${0===i.length||m}
                @click=${()=>this._setCoversPosition(e,i,0)}
              >
                <ha-icon icon="mdi:arrow-down"></ha-icon>
              </button>
            </div>`:Y}
        ${h?Y:D}
      </div>
    `}_targetCovers(e){return this._config?.cover?[this._config.cover]:e.managed_covers}_currentPosition(e){const t=e.entities.target_position_sensor;if(!t)return null;const o=this.hass.states[t];if(!o)return null;const i=parseFloat(o.state);return Number.isNaN(i)?null:i}_liveCoverPosition(e,t){return t?no(this.hass,e.cover_type,t):null}_manualOverrideOn(e){const t=e.entities.manual_override_binary;return!!t&&"on"===this.hass.states[t]?.state}_switchOn(e,t){const o=e.entities[t];return!o||"off"!==this.hass.states[o]?.state}_setCoversPosition(e,t,o){0!==t.length&&("cover_tilt"===e.cover_type?this.hass.callService("cover","set_cover_tilt_position",{entity_id:t,tilt_position:o}):this.hass.callService("cover","set_cover_position",{entity_id:t,position:o}))}_stopCovers(e){0!==e.length&&this.hass.callService("cover","stop_cover",{entity_id:e})}_resume(e){const t=e.entities.reset_override_button;t&&ti(oi(this.hass,e.entities.target_position_sensor))&&this.hass.callService("button","press",{entity_id:t})}_tapActionConfig(){const e=this._config?.tap_action;if("string"!=typeof e)return e}_isFullyInert(e){return!!(e=>!!e&&"none"===e.action)(this._tapActionConfig())&&!Xo(e.hold_action)&&!Xo(e.double_tap_action)}_fireAction(e){if(!this._config||!this.hass)return;const t=this._tapActionConfig();if("tap"===e&&void 0===t)return this._dialogOpen=!0,void this.dispatchEvent(new CustomEvent("acp-tile-tap",{bubbles:!0,composed:!0}));const o=this._resolvedCoverFromState();((e,t,o,i)=>{let s;"double_tap"===i&&o.double_tap_action?s=o.double_tap_action:"hold"===i&&o.hold_action?s=o.hold_action:"tap"===i&&o.tap_action&&(s=o.tap_action),((e,t,o,i)=>{if(i||(i={action:"more-info"}),!i.confirmation||i.confirmation.exemptions&&i.confirmation.exemptions.some(e=>e.user===t.user.id)||(qo("warning"),confirm(i.confirmation.text||`Are you sure you want to ${i.action}?`)))switch(i.action){case"more-info":(o.entity||o.camera_image)&&Qo(e,"hass-more-info",{entityId:o.entity?o.entity:o.camera_image});break;case"navigate":i.navigation_path&&((e,t,o=!1)=>{o?history.replaceState(null,"",t):history.pushState(null,"",t),Qo(window,"location-changed",{replace:o})})(0,i.navigation_path);break;case"url":i.url_path&&window.open(i.url_path);break;case"toggle":o.entity&&(((e,t)=>{((e,t,o=!0)=>{const i=function(e){return e.substr(0,e.indexOf("."))}(t),s="group"===i?"homeassistant":i;let n;switch(i){case"lock":n=o?"unlock":"lock";break;case"cover":n=o?"open_cover":"close_cover";break;default:n=o?"turn_on":"turn_off"}e.callService(s,n,{entity_id:t})})(e,t,Ho.includes(e.states[t].state))})(t,o.entity),qo("success"));break;case"call-service":{if(!i.service)return void qo("failure");const[e,o]=i.service.split(".",2);t.callService(e,o,i.service_data,i.target),qo("success");break}case"fire-dom-event":Qo(e,"ll-custom",i)}})(e,t,o,s)})(this,this.hass,{entity:o,tap_action:t,hold_action:this._config.hold_action,double_tap_action:this._config.double_tap_action},e)}_resolvedCoverFromState(){if(this._config?.cover)return this._config.cover;if(null===this._registry)return;const e=this._discovered??this._memo(this.hass,this._config,this._registry);return e?.managed_covers[0]}_notFoundLabel(){const e=yt(this._config);return e?xt(e):""}_stop(e){e.stopPropagation()}};vi.styles=r`
    :host {
      display: block;
      height: 100%;
    }
    ha-card {
      padding: 6px 10px;
      overflow: hidden;
      height: 100%;
      box-sizing: border-box;
      /* Center the tile body vertically so a taller-than-default grid cell
         (Sections drag-resize) keeps the content centered rather than top-aligned. */
      display: flex;
      flex-direction: column;
      justify-content: center;
      /* In HA's "Sections" view the tile width is driven by the dashboard
         column, not the viewport, so @media can't see the squeeze. Make the
         card a query container so the detailed layout can reflow its controls
         onto their own row once the column gets narrow. */
      container-type: inline-size;
    }
    .tile-body {
      display: grid;
      /* Position column is fixed-width so the controls land at the same x
         across stacked tiles regardless of the digit count (87% vs 100%). */
      grid-template-columns: 24px minmax(0, 1fr) 3rem auto auto;
      grid-template-areas: 'icon label position controls badge';
      align-items: center;
      column-gap: 8px;
      row-gap: 2px;
      cursor: pointer;
      user-select: none;
      min-width: 0;
    }
    /* When the state label is rendered ("Open · 12%") the position cell needs
       to grow to fit variable-width text. */
    .tile-body.has-state-label {
      grid-template-columns: 24px minmax(0, 1fr) auto auto auto;
    }
    /* Detailed layout: title row, then a state row that inlines the position
       text + contextual badge (.detail-line). Icon spans both rows so it's
       vertically centered; controls float to the right of rows 1-2 (HA
       tile-card style). */
    .tile-body.detailed {
      grid-template-columns: 24px minmax(0, 1fr) auto auto;
      grid-template-rows: auto auto;
      grid-template-areas:
        'icon label       auto-line   controls'
        'icon detail-line detail-line controls';
      row-gap: 2px;
    }
    /* The standalone Auto indicator rides right-aligned on the title row —
       same line as the cover name, above the state line — so the tile stays
       two text lines tall. When absent the cell collapses to 0px. */
    .auto-line {
      grid-area: auto-line;
      display: flex;
      justify-content: flex-end;
      align-items: center;
      min-width: 0;
    }
    .auto-line acp-tile-badge {
      overflow: visible;
    }
    .detail-line {
      grid-area: detail-line;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px;
      min-width: 0;
    }
    .battery {
      margin-left: 6px;
      font-size: 0.72rem;
      color: var(--secondary-text-color);
      white-space: nowrap;
    }
    .battery ha-icon {
      --mdc-icon-size: 13px;
      vertical-align: -2px;
    }
    .battery.warn {
      color: var(--warning-color, #e6a02e);
      font-weight: 600;
    }
    .battery.low {
      color: var(--error-color, #db4437);
      font-weight: 600;
    }
    .detail-line .position {
      padding: 0;
      text-align: left;
      /* Push the badge to the right edge of the row so it sits flush against
         the controls column. */
      margin-right: auto;
    }
    .detail-line acp-tile-badge {
      overflow: visible;
    }
    .tile-body.detailed.has-state-label {
      grid-template-columns: 24px minmax(0, 1fr) auto auto;
      grid-template-rows: auto auto;
      grid-template-areas:
        'icon label       auto-line   controls'
        'icon detail-line detail-line controls';
    }
    .tile-body.detailed.has-summary .label {
      display: flex;
      align-items: baseline;
      gap: 8px;
      min-width: 0;
    }
    .tile-body.detailed.has-summary .label .title {
      flex: 1 1 auto;
      min-width: 0;
    }
    .tile-body.detailed.has-summary .label .inline-summary {
      flex: 0 1 auto;
      text-align: right;
    }
    .tile-body.detailed .position {
      text-align: left;
      padding: 0;
    }
    .tile-body.detailed .controls {
      align-self: center;
      gap: 6px;
    }
    .tile-body.detailed .controls button {
      width: 56px;
      height: 44px;
      border-radius: 12px;
      border: none;
      background: var(--secondary-background-color, rgba(127, 127, 127, 0.15));
    }
    .tile-body.detailed .controls button ha-icon {
      --mdc-icon-size: 22px;
      color: var(--primary-text-color);
    }
    .tile-body.detailed .controls button:hover {
      background: var(--divider-color, rgba(127, 127, 127, 0.25));
    }
    .tile-body.detailed .cover-icon-wrap {
      place-self: center;
    }
    .tile-body[role='group'] {
      cursor: default;
    }
    .cover-icon-wrap {
      grid-area: icon;
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 24px;
      height: 24px;
    }
    .cover-icon {
      --mdc-icon-size: 22px;
      color: var(--primary-text-color);
    }
    .label {
      grid-area: label;
      min-width: 0;
    }
    .title {
      font-size: 0.95rem;
      font-weight: 500;
      color: var(--primary-text-color);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .summary {
      font-size: 0.78rem;
      color: var(--secondary-text-color);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      min-width: 0;
    }
    .position {
      grid-area: position;
      font-size: 0.85rem;
      font-variant-numeric: tabular-nums;
      color: var(--primary-text-color);
      padding: 0 4px;
      text-align: right;
    }
    .controls {
      grid-area: controls;
      display: inline-flex;
      gap: 2px;
    }
    .controls button {
      width: 26px;
      height: 26px;
      border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
      border-radius: 4px;
      background: var(--card-background-color, white);
      color: var(--primary-text-color);
      cursor: pointer;
      font-size: 0.8rem;
      line-height: 1;
      padding: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
    .controls button ha-icon {
      --mdc-icon-size: 16px;
      color: var(--primary-text-color);
      line-height: 0;
    }
    .controls button:hover {
      background: var(--secondary-background-color);
    }
    .controls button:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }
    acp-tile-badge {
      grid-area: badge;
      min-width: 0;
      overflow: hidden;
    }
    /* Floating-tooltip cursor lifecycle for the tooltip carriers inside the
       tile. Help hint on hover, default once OUR bubble appears. */
    [data-tooltip]:hover {
      cursor: help;
    }
    [data-tooltip][acp-tt-shown] {
      cursor: default;
    }
    /* Reflow: drop the ↑■▼ controls onto their own full-width row beneath the
       name so the cover name gets the whole column. Two triggers:
         1. a phone: the whole viewport is narrow (≤500px) AND the tile is
            near full-width (≤480px).
         2. a desktop "Sections" narrow column (≤340px). */
    @media (max-width: 500px) {
      @container (max-width: 480px) {
        .tile-body.detailed,
        .tile-body.detailed.has-state-label {
          grid-template-columns: 24px minmax(0, 1fr) auto;
          grid-template-rows: auto auto auto;
          grid-template-areas:
            'icon label       auto-line'
            'icon detail-line detail-line'
            'controls controls controls';
        }
        .tile-body.detailed .controls {
          margin-top: 4px;
          gap: 6px;
          justify-content: space-between;
        }
        .tile-body.detailed .controls button {
          flex: 1 1 0;
          width: auto;
          height: 40px;
        }
      }
    }
    @container (max-width: 340px) {
      .tile-body.detailed,
      .tile-body.detailed.has-state-label {
        grid-template-columns: 24px minmax(0, 1fr) auto;
        grid-template-rows: auto auto auto;
        grid-template-areas:
          'icon label       auto-line'
          'icon detail-line detail-line'
          'controls controls controls';
      }
      .tile-body.detailed .controls {
        margin-top: 4px;
        gap: 6px;
        justify-content: space-between;
      }
      .tile-body.detailed .controls button {
        flex: 1 1 0;
        width: auto;
        height: 40px;
      }
    }
    .empty {
      padding: 12px;
      text-align: center;
    }
    .dim {
      color: var(--secondary-text-color);
      margin: 0;
    }
  `,e([ge({attribute:!1})],vi.prototype,"hass",void 0),e([me()],vi.prototype,"_config",void 0),e([me()],vi.prototype,"_registry",void 0),e([me()],vi.prototype,"_registryError",void 0),e([me()],vi.prototype,"_dialogOpen",void 0),vi=e([he(xe)],vi),window.customCards=window.customCards||[],window.customCards.some(e=>e.type===xe)||window.customCards.push({type:xe,name:"Adaptive Cover — Tile",description:"Compact chip-style tile for one Adaptive Cover instance: icon, name, position, ↑■↓, contextual badge.",preview:!0,documentationURL:"https://github.com/mrvollger/adaptive-cover-card"});const yi={summer:"mdi:weather-sunny",winter:"mdi:snowflake",intermediate:"mdi:weather-partly-cloudy",basic:"mdi:sun-compass"};let wi=class extends ce{constructor(){super(...arguments),this.compact=!1}shouldUpdate(e){if(e.size>1||!e.has("hass"))return!0;const t=e.get("hass"),o=this.discovered?.entities;return fe(t,this.hass,[o?.control_status_sensor,o?.climate_mode_switch])}render(){if(!this.hass||!this.discovered)return Y;const e=this.discovered.entities.climate_mode_switch;if(!e)return Y;const t=this.discovered.entities.control_status_sensor;if(!t)return Y;const o=this.hass.states[t];if(!o||"unavailable"===o.state)return Y;const i="off"===this.hass.states[e]?.state;if(i||"unknown"===o.state||""===o.state){const e=Ve(i?"climate.mode_off":"climate.standby"),t=i?"mdi:power-off":"mdi:thermostat";return G`
        <div class="wrap">
          <div class="head">
            <span class="label">${Ve("climate.title")}</span>
          </div>
          <div class="strategy standby">
            <ha-icon icon=${t}></ha-icon>
            <span class="strategy-name dim">${e}</span>
          </div>
        </div>
      `}const s=o.state,n=yi[s]??"mdi:thermostat",r=this.hass.formatEntityState,a="function"==typeof r?r(o)??s:s;return G`
      <div class="wrap">
        <div class="head">
          <span class="label">${Ve("climate.title")}</span>
        </div>
        <div class="strategy">
          <ha-icon icon=${n}></ha-icon>
          <span class="strategy-name">${a}</span>
        </div>
      </div>
    `}};wi.styles=r`
    :host {
      display: block;
    }
    .wrap {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .head {
      display: flex;
      justify-content: space-between;
      font-size: 0.78rem;
      color: var(--secondary-text-color);
    }
    .label {
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }
    .strategy {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.95rem;
      font-weight: 500;
    }
    .strategy ha-icon {
      --mdc-icon-size: 20px;
      color: var(--primary-color);
    }
    .strategy.standby ha-icon {
      color: var(--secondary-text-color);
    }
    :host([compact]) .strategy {
      font-size: 0.85rem;
    }
    :host([compact]) .head {
      display: none;
    }
    .dim {
      color: var(--secondary-text-color);
    }
  `,e([ge({attribute:!1})],wi.prototype,"hass",void 0),e([ge({attribute:!1})],wi.prototype,"discovered",void 0),e([ge({type:Boolean,reflect:!0})],wi.prototype,"compact",void 0),wi=e([he("acp-climate-panel")],wi);const bi=[{key:"sky",labelKey:"editor.main.section_sky_label",descKey:"editor.main.section_sky_desc"},{key:"elevation",labelKey:"editor.main.section_elevation_label",descKey:"editor.main.section_elevation_desc"},{key:"decision",labelKey:"editor.main.section_decision_label",descKey:"editor.main.section_decision_desc"},{key:"covers",labelKey:"editor.main.section_covers_label",descKey:"editor.main.section_covers_desc"},{key:"overrides",labelKey:"editor.main.section_overrides_label",descKey:"editor.main.section_overrides_desc"},{key:"climate",labelKey:"editor.main.section_climate_label",descKey:"editor.main.section_climate_desc"}],xi=bi.filter(e=>!1!==e.enabledByDefault).map(e=>e.key);let $i=class extends ce{constructor(){super(...arguments),this._windows=null,this._windowsError=null,this._fetchInFlight=!1}setConfig(e){this._config=e}updated(e){e.has("hass")&&this.hass&&!this._windows&&!this._fetchInFlight&&(this._fetchInFlight=!0,Qt(this.hass).then(e=>{this._windows=e,this._windowsError=null,this._config?.window||this._config?.entry_id||this._config?.cover||1!==e.length||this._emit($t(this._config??{type:""},e[0].window_key))}).catch(e=>{this._windowsError=e?.message??"failed to load windows"}).finally(()=>{this._fetchInFlight=!1}))}get _currentSections(){return this._config?.show_sections??xi}_emit(e){this._config=e,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e},bubbles:!0,composed:!0}))}_onWindowChange(e){const t=e.target.value;t!==kt(this._config)&&this._emit($t(this._config??{type:""},t))}_onSectionToggle(e,t){const o=new Set(this._currentSections);t?o.add(e):o.delete(e);const i=bi.map(e=>e.key).filter(e=>o.has(e));this._emit({...this._config??{type:""},show_sections:i})}_onCompactToggle(e){this._emit({...this._config??{type:""},compact:e})}_onCompassStatsToggle(e){this._emit({...this._config??{type:""},show_compass_stats:e})}_onCompassLegendToggle(e){this._emit({...this._config??{type:""},show_compass_legend:e})}_onMoonToggle(e){this._emit({...this._config??{type:""},show_moon:e})}_onHideInactiveToggle(e){this._emit({...this._config??{type:""},hide_inactive_handlers:e})}_onNorthOffsetChange(e){const t=parseFloat(e.target.value),o=Number.isFinite(t)?t:0;this._emit({...this._config??{type:""},north_offset:o})}_onControlToggle(e,t){const o=this._config??{type:""};this._emit({...o,controls:{...o.controls,[e]:t}})}_onCoverColorChange(e){const t=this._config??{type:""};this._emit({...t,cover_colors:[e]})}_onCoverColorReset(){const e={...this._config??{type:""}};delete e.cover_colors,this._emit(e)}render(){if(!this._config)return Y;const e=new Set(this._currentSections);return G`
      <div class="form">
        <div class="section">
          <label class="field-label">${Ve("editor.common.window")}</label>
          ${this._renderWindowPicker()}
        </div>

        <div class="section">
          <label class="field-label">${Ve("editor.main.sections")}</label>
          <div class="hint">${Ve("editor.main.sections_hint")}</div>
          ${bi.map(t=>G`
              <label class="toggle-row">
                <input
                  type="checkbox"
                  .checked=${e.has(t.key)}
                  @change=${e=>this._onSectionToggle(t.key,e.target.checked)}
                />
                <span class="toggle-text">
                  <span class="toggle-label">${Ve(t.labelKey)}</span>
                  <span class="toggle-desc">${Ve(t.descKey)}</span>
                </span>
              </label>
            `)}
        </div>

        <div class="section">
          <label class="field-label">${Ve("editor.main.controls")}</label>
          <div class="hint">${Ve("editor.main.controls_hint")}</div>
          <label class="toggle-row">
            <input
              type="checkbox"
              .checked=${this._config.controls?.integration_enabled??!0}
              @change=${e=>this._onControlToggle("integration_enabled",e.target.checked)}
            />
            <span class="toggle-text">
              <span class="toggle-label">${Ve("editor.main.integration_pill_label")}</span>
              <span class="toggle-desc">${Ve("editor.main.integration_pill_desc")}</span>
            </span>
          </label>
          <label class="toggle-row">
            <input
              type="checkbox"
              .checked=${this._config.controls?.automatic_control??!0}
              @change=${e=>this._onControlToggle("automatic_control",e.target.checked)}
            />
            <span class="toggle-text">
              <span class="toggle-label">${Ve("editor.main.automatic_pill_label")}</span>
              <span class="toggle-desc">${Ve("editor.main.automatic_pill_desc")}</span>
            </span>
          </label>
          <label class="toggle-row">
            <input
              type="checkbox"
              .checked=${this._config.controls?.reset_manual_override??!0}
              @change=${e=>this._onControlToggle("reset_manual_override",e.target.checked)}
            />
            <span class="toggle-text">
              <span class="toggle-label">${Ve("editor.main.reset_button_label")}</span>
              <span class="toggle-desc">${Ve("editor.main.reset_button_desc")}</span>
            </span>
          </label>
        </div>

        ${kt(this._config)||this._config.cover?G`
              <div class="section">
                <label class="field-label">${Ve("editor.compass.cover_colors")}</label>
                <div class="hint">${Ve("editor.compass.cover_colors_hint")}</div>
                ${(()=>{const e=this._config.cover_colors?.[0]??null,t=e??Io(0);return G`
                    <div class="color-row">
                      <input
                        type="color"
                        .value=${t}
                        @change=${e=>this._onCoverColorChange(e.target.value)}
                      />
                      <span class="toggle-text">
                        <span class="toggle-desc"
                          >${e||Ve("editor.compass.default_color")}</span
                        >
                      </span>
                      <button
                        type="button"
                        class="reset-btn"
                        ?disabled=${!e}
                        @click=${()=>this._onCoverColorReset()}
                      >
                        ${Ve("editor.common.reset")}
                      </button>
                    </div>
                  `})()}
              </div>
            `:Y}

        <div class="section">
          <label class="field-label">${Ve("editor.main.display")}</label>
          <label class="toggle-row">
            <input
              type="checkbox"
              .checked=${this._config.compact??!1}
              @change=${e=>this._onCompactToggle(e.target.checked)}
            />
            <span class="toggle-text">
              <span class="toggle-label">${Ve("editor.main.compact_label")}</span>
              <span class="toggle-desc">${Ve("editor.main.compact_desc")}</span>
            </span>
          </label>
          <label class="toggle-row">
            <input
              type="checkbox"
              .checked=${this._config.show_compass_stats??!0}
              @change=${e=>this._onCompassStatsToggle(e.target.checked)}
            />
            <span class="toggle-text">
              <span class="toggle-label">${Ve("editor.main.show_compass_stats_label")}</span>
              <span class="toggle-desc">${Ve("editor.main.show_compass_stats_desc")}</span>
            </span>
          </label>
          <label class="toggle-row">
            <input
              type="checkbox"
              .checked=${this._config.show_compass_legend??!0}
              @change=${e=>this._onCompassLegendToggle(e.target.checked)}
            />
            <span class="toggle-text">
              <span class="toggle-label">${Ve("editor.main.show_compass_legend_label")}</span>
              <span class="toggle-desc">${Ve("editor.main.show_compass_legend_desc")}</span>
            </span>
          </label>
          <label class="toggle-row">
            <input
              type="checkbox"
              .checked=${this._config.show_moon??!1}
              @change=${e=>this._onMoonToggle(e.target.checked)}
            />
            <span class="toggle-text">
              <span class="toggle-label">${Ve("editor.main.show_moon_label")}</span>
              <span class="toggle-desc">${Ve("editor.main.show_moon_desc")}</span>
            </span>
          </label>
          <label class="toggle-row">
            <input
              type="checkbox"
              .checked=${this._config.hide_inactive_handlers??!1}
              @change=${e=>this._onHideInactiveToggle(e.target.checked)}
            />
            <span class="toggle-text">
              <span class="toggle-label">${Ve("editor.main.hide_inactive_label")}</span>
              <span class="toggle-desc">${Ve("editor.main.hide_inactive_desc")}</span>
            </span>
          </label>
        </div>

        <div class="section">
          <label class="field-label">${Ve("editor.common.north_offset")}</label>
          <div class="hint">${Ve("editor.common.north_offset_hint")}</div>
          <input
            type="number"
            class="text-input"
            .value=${String(this._config.north_offset??0)}
            step="1"
            inputmode="numeric"
            @change=${this._onNorthOffsetChange}
          />
        </div>
        ${pi()}
      </div>
    `}_renderWindowPicker(){const e=kt(this._config);return this._windowsError?G`
        <div class="error">${Ve("editor.common.load_failed",{error:this._windowsError})}</div>
        <input
          type="text"
          .value=${e}
          placeholder=${Ve("editor.common.window_manual_placeholder")}
          @change=${this._onWindowChange}
          class="text-input"
        />
      `:this._windows?0===this._windows.length?G`
        <div class="error">
          ${Ve("editor.common.no_entries")}
          <code>${Ve("editor.common.no_entries_path")}</code>${Ve("editor.common.no_entries_then")}
        </div>
      `:G`
      <select class="select" .value=${e} @change=${this._onWindowChange}>
        ${e&&!this._windows.some(t=>t.window_key===e)?G`<option value=${e}>
              ${Ve("editor.common.unknown_entry",{entry:e})}
            </option>`:Y}
        ${this._windows.map(t=>G`
            <option value=${t.window_key} ?selected=${t.window_key===e}>${t.title}</option>
          `)}
      </select>
    `:G`<div class="hint">${Ve("editor.common.loading_entries")}</div>`}};$i.styles=r`
    :host {
      display: block;
    }
    .form {
      display: flex;
      flex-direction: column;
      gap: 16px;
      padding: 8px 0;
    }
    .section {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .field-label {
      font-weight: 500;
      font-size: 0.88rem;
      color: var(--primary-text-color);
    }
    .hint {
      font-size: 0.78rem;
      color: var(--secondary-text-color);
    }
    .error {
      font-size: 0.82rem;
      color: var(--error-color, crimson);
    }
    .select,
    .text-input {
      width: 100%;
      padding: 8px 10px;
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      background: var(--card-background-color, transparent);
      color: var(--primary-text-color);
      font-size: 0.9rem;
      font-family: inherit;
    }
    .select:focus,
    .text-input:focus {
      outline: none;
      border-color: var(--primary-color);
    }
    .toggle-row {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 6px 0;
      cursor: pointer;
    }
    .toggle-row input[type='checkbox'] {
      margin-top: 3px;
      accent-color: var(--primary-color);
      width: 16px;
      height: 16px;
    }
    .toggle-text {
      display: flex;
      flex-direction: column;
    }
    .toggle-label {
      font-size: 0.88rem;
      color: var(--primary-text-color);
    }
    .toggle-desc {
      font-size: 0.74rem;
      color: var(--secondary-text-color);
    }
    .color-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 4px 0;
    }
    .color-row input[type='color'] {
      width: 32px;
      height: 32px;
      border: 1px solid var(--divider-color);
      border-radius: 4px;
      padding: 2px;
      background: none;
      cursor: pointer;
      flex-shrink: 0;
    }
    .color-row .toggle-text {
      flex: 1;
    }
    .reset-btn {
      background: none;
      border: 1px solid var(--divider-color);
      border-radius: 4px;
      padding: 3px 8px;
      font-size: 0.78rem;
      color: var(--secondary-text-color);
      cursor: pointer;
      flex-shrink: 0;
    }
    .reset-btn:disabled {
      opacity: 0.35;
      cursor: default;
    }
    code {
      background: var(--code-editor-background-color, rgba(0, 0, 0, 0.08));
      padding: 1px 5px;
      border-radius: 3px;
      font-size: 0.85em;
    }
    .version-footer {
      font-size: 0.7rem;
      text-align: right;
    }
    .dim {
      color: var(--secondary-text-color);
    }
  `,e([ge({attribute:!1})],$i.prototype,"hass",void 0),e([me()],$i.prototype,"_config",void 0),e([me()],$i.prototype,"_windows",void 0),e([me()],$i.prototype,"_windowsError",void 0),$i=e([he(ye)],$i);const ki=[{key:"compact",labelKey:"editor.compass.toggle_compact_label",descKey:"editor.compass.toggle_compact_desc",defaultOn:!1},{key:"show_legend",labelKey:"editor.compass.toggle_legend_label",descKey:"editor.compass.toggle_legend_desc",defaultOn:!0},{key:"show_stats",labelKey:"editor.compass.toggle_stats_label",descKey:"editor.compass.toggle_stats_desc",defaultOn:!0},{key:"show_moon",labelKey:"editor.compass.toggle_moon_label",descKey:"editor.compass.toggle_moon_desc",defaultOn:!1},{key:"show_cardinals",labelKey:"editor.compass.toggle_cardinals_label",descKey:"editor.compass.toggle_cardinals_desc",defaultOn:!0},{key:"show_blind_spot",labelKey:"editor.compass.toggle_blind_spot_label",descKey:"editor.compass.toggle_blind_spot_desc",defaultOn:!0},{key:"show_sun_path",labelKey:"editor.compass.toggle_sun_path_label",descKey:"editor.compass.toggle_sun_path_desc",defaultOn:!0},{key:"show_sunrise_sunset",labelKey:"editor.compass.toggle_sunrise_sunset_label",descKey:"editor.compass.toggle_sunrise_sunset_desc",defaultOn:!0},{key:"show_cover_fill",labelKey:"editor.compass.toggle_cover_fill_label",descKey:"editor.compass.toggle_cover_fill_desc",defaultOn:!0},{key:"show_window_arrow",labelKey:"editor.compass.toggle_window_arrow_label",descKey:"editor.compass.toggle_window_arrow_desc",defaultOn:!0},{key:"show_elevation_chart",labelKey:"editor.compass.toggle_elevation_chart_label",descKey:"editor.compass.toggle_elevation_chart_desc",defaultOn:!0}];let Si=class extends ce{constructor(){super(...arguments),this._windows=null,this._windowsError=null,this._fetchInFlight=!1}setConfig(e){this._config=e}updated(e){e.has("hass")&&this.hass&&!this._windows&&!this._fetchInFlight&&(this._fetchInFlight=!0,Qt(this.hass).then(e=>{this._windows=e,this._windowsError=null}).catch(e=>{this._windowsError=e?.message??"failed to load windows"}).finally(()=>{this._fetchInFlight=!1}))}_emit(e){this._config=e,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e},bubbles:!0,composed:!0}))}_baseConfig(){return this._config??{type:`custom:${we}`,windows:[]}}_trimColors(e){let t=-1;for(let o=0;o<e.length;o++)e[o]&&(t=o);if(!(t<0))return e.slice(0,t+1)}_emitWithColors(e,t,o){const i=this._trimColors(t),{cover_colors:s,...n}=e,r=i?{...n,...o,cover_colors:i}:{...n,...o};this._emit(r)}_onCoverColorChange(e,t){const o=this._baseConfig(),i=[...o.cover_colors??[]];for(;i.length<=e;)i.push(null);i[e]=t,this._emitWithColors(o,i)}_onCoverColorReset(e){const t=this._baseConfig(),o=[...t.cover_colors??[]];e<o.length&&(o[e]=null),this._emitWithColors(t,o)}_selectedKeys(e){return[...e.windows??[],...e.entry_ids??[]]}_onWindowToggle(e,t){const o=this._baseConfig(),i=new Set(this._selectedKeys(o));t?i.add(e):i.delete(e);const s=(this._windows??[]).map(e=>e.window_key).filter(e=>i.has(e)),n={...o,windows:s};delete n.entry_ids;const r=wt(o).map(bt),a=o.cover_colors??[],l=wt(n).map(e=>{const t=r.indexOf(bt(e));return t>=0?a[t]??null:null});this._emitWithColors(n,l)}_refTitle(e){if("cover"===e.kind){const t=this.hass?.states?.[e.entity_id]?.attributes?.friendly_name;return"string"==typeof t&&t?t:e.entity_id}return this._windows?.find(t=>t.window_key===e.key)?.title??xt(e)}_onToggle(e,t){this._emit({...this._baseConfig(),[e]:t})}_onNorthOffsetChange(e){const t=parseFloat(e.target.value),o=Number.isFinite(t)?t:0;this._emit({...this._baseConfig(),north_offset:o})}_onTitleChange(e){const t=e.target.value,o=this._baseConfig();if(t)this._emit({...o,title:t});else{const{title:e,...t}=o;this._emit(t)}}render(){if(!this._config)return Y;const e=new Set(this._selectedKeys(this._config)),t=wt(this._config);return G`
      <div class="form">
        <div class="section">
          <label class="field-label">${Ve("editor.compass.instances")}</label>
          <div class="hint">${Ve("editor.compass.instances_hint")}</div>
          ${this._renderWindowPicker(e)}
        </div>

        <div class="section">
          <label class="field-label">${Ve("editor.common.title_optional")}</label>
          <input
            type="text"
            class="text-input"
            .value=${this._config.title??""}
            placeholder=${Ve("editor.common.title_placeholder")}
            @change=${this._onTitleChange}
          />
        </div>

        ${t.length>0?G`
              <div class="section">
                <label class="field-label">${Ve("editor.compass.cover_colors")}</label>
                <div class="hint">${Ve("editor.compass.cover_colors_hint")}</div>
                ${t.map((e,t)=>{const o=this._config.cover_colors?.[t]??null,i=o??Io(t);return G`
                    <div class="color-row">
                      <input
                        type="color"
                        .value=${i}
                        @change=${e=>this._onCoverColorChange(t,e.target.value)}
                      />
                      <span class="toggle-text">
                        <span class="toggle-label">${this._refTitle(e)}</span>
                        <span class="toggle-desc"
                          >${o||Ve("editor.compass.default_color")}</span
                        >
                      </span>
                      <button
                        type="button"
                        class="reset-btn"
                        ?disabled=${!o}
                        @click=${()=>this._onCoverColorReset(t)}
                      >
                        ${Ve("editor.common.reset")}
                      </button>
                    </div>
                  `})}
              </div>
            `:Y}

        <div class="section">
          <label class="field-label">${Ve("editor.compass.display")}</label>
          ${ki.map(e=>G`
              <label class="toggle-row">
                <input
                  type="checkbox"
                  .checked=${this._config[e.key]??e.defaultOn}
                  @change=${t=>this._onToggle(e.key,t.target.checked)}
                />
                <span class="toggle-text">
                  <span class="toggle-label">${Ve(e.labelKey)}</span>
                  <span class="toggle-desc">${Ve(e.descKey)}</span>
                </span>
              </label>
            `)}
        </div>

        <div class="section">
          <label class="field-label">${Ve("editor.common.north_offset")}</label>
          <div class="hint">${Ve("editor.common.north_offset_hint")}</div>
          <input
            type="number"
            class="text-input"
            .value=${String(this._config.north_offset??0)}
            step="1"
            inputmode="numeric"
            @change=${this._onNorthOffsetChange}
          />
        </div>
        ${pi()}
      </div>
    `}_renderWindowPicker(e){return this._windowsError?G`<div class="error">
        ${Ve("editor.common.load_failed",{error:this._windowsError})}
      </div>`:this._windows?0===this._windows.length?G`
        <div class="error">
          ${Ve("editor.common.no_entries")}
          <code>${Ve("editor.common.no_entries_path")}</code>${Ve("editor.common.no_entries_then")}
        </div>
      `:G`
      <div class="entry-list">
        ${this._windows.map(t=>G`
            <label class="toggle-row">
              <input
                type="checkbox"
                .checked=${e.has(t.window_key)}
                @change=${e=>this._onWindowToggle(t.window_key,e.target.checked)}
              />
              <span class="toggle-text">
                <span class="toggle-label">${t.title}</span>
                <span class="toggle-desc">${t.cover??t.window_key}</span>
              </span>
            </label>
          `)}
      </div>
    `:G`<div class="hint">${Ve("editor.common.loading_entries")}</div>`}};Si.styles=r`
    :host {
      display: block;
    }
    .form {
      display: flex;
      flex-direction: column;
      gap: 16px;
      padding: 8px 0;
    }
    .section {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .field-label {
      font-weight: 500;
      font-size: 0.88rem;
      color: var(--primary-text-color);
    }
    .hint {
      font-size: 0.78rem;
      color: var(--secondary-text-color);
    }
    .error {
      font-size: 0.82rem;
      color: var(--error-color, crimson);
    }
    .text-input {
      width: 100%;
      padding: 8px 10px;
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      background: var(--card-background-color, transparent);
      color: var(--primary-text-color);
      font-size: 0.9rem;
      font-family: inherit;
    }
    .text-input:focus {
      outline: none;
      border-color: var(--primary-color);
    }
    .toggle-row {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 6px 0;
      cursor: pointer;
    }
    .toggle-row input[type='checkbox'] {
      margin-top: 3px;
      accent-color: var(--primary-color);
      width: 16px;
      height: 16px;
    }
    .toggle-text {
      display: flex;
      flex-direction: column;
    }
    .toggle-label {
      font-size: 0.88rem;
      color: var(--primary-text-color);
    }
    .toggle-desc {
      font-size: 0.74rem;
      color: var(--secondary-text-color);
    }
    .entry-list {
      display: flex;
      flex-direction: column;
    }
    .color-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 4px 0;
    }
    .color-row input[type='color'] {
      width: 32px;
      height: 32px;
      border: 1px solid var(--divider-color);
      border-radius: 4px;
      padding: 2px;
      background: none;
      cursor: pointer;
      flex-shrink: 0;
    }
    .color-row .toggle-text {
      flex: 1;
    }
    .reset-btn {
      background: none;
      border: 1px solid var(--divider-color);
      border-radius: 4px;
      padding: 3px 8px;
      font-size: 0.78rem;
      color: var(--secondary-text-color);
      cursor: pointer;
      flex-shrink: 0;
    }
    .reset-btn:disabled {
      opacity: 0.35;
      cursor: default;
    }
    code {
      background: var(--code-editor-background-color, rgba(0, 0, 0, 0.08));
      padding: 1px 5px;
      border-radius: 3px;
      font-size: 0.85em;
    }
    .version-footer {
      font-size: 0.7rem;
      text-align: right;
    }
    .dim {
      color: var(--secondary-text-color);
    }
  `,e([ge({attribute:!1})],Si.prototype,"hass",void 0),e([me()],Si.prototype,"_config",void 0),e([me()],Si.prototype,"_windows",void 0),e([me()],Si.prototype,"_windowsError",void 0),Si=e([he(be)],Si);let Ai=class extends ce{constructor(){super(...arguments),this._registry=null,this._registryError=null,this._unsubRegistry=null,this._fetchInFlight=!1,this._listMemo=function(){const e=new Map;let t=[],o=[],i={list:[],missing:[]};return(s,n,r)=>{const a=n.map(bt),l=n.map((t,o)=>{let i=e.get(a[o]);return i||(i=Bt(),e.set(a[o],i)),i(s,t,r)});if(e.size>a.length)for(const t of e.keys())a.includes(t)||e.delete(t);const c=t.length===a.length&&t.every((e,t)=>e===a[t])&&o.length===l.length&&o.every((e,t)=>e===l[t]);if(c)return i;t=a,o=l;const d=[],h=[],u=new Set;return n.forEach((e,t)=>{const o=l[t];o?u.has(o.window_key)||(u.add(o.window_key),d.push(o)):h.push(e)}),i={list:d,missing:h},i}}(),this._discoveredResult={list:[],missing:[]},this._refs=[]}setConfig(e){const t=["windows","covers","entry_ids"].filter(t=>void 0!==e?.[t]);for(const o of t){const t=e[o];if(!Array.isArray(t))throw new Error(`adaptive-cover-sky-compass-card: \`${o}\` must be an array`);if(t.some(e=>"string"!=typeof e||0===e.length))throw new Error(`adaptive-cover-sky-compass-card: every \`${o}\` item must be a non-empty string`)}const o=wt(e);if(0===o.length)throw new Error("adaptive-cover-sky-compass-card: list at least one window in `windows` (or `covers`, or the legacy `entry_ids`)");this._config={...e};for(const o of t)this._config[o]=[...e[o]];if(this._refs=o,e.tooltips&&gt(e.tooltips),null===this._registry){const e=o.map(e=>Xt.get(bt(e))?.entries);e.every(e=>void 0!==e)&&(this._registry=e.flat())}}getCardSize(){return 4}getGridOptions(){return{columns:12,rows:"auto",min_columns:6,max_columns:12}}static async getConfigElement(){return document.createElement(be)}static async getStubConfig(e){let t=[];try{const o=await Qt(e);o[0]&&(t=[o[0].window_key])}catch{}return{type:`custom:${we}`,windows:t}}connectedCallback(){if(super.connectedCallback(),null===this._registry){const e=Lt();e&&(this._registry=e)}this.hass&&this._ensureRegistry()}disconnectedCallback(){super.disconnectedCallback(),this._unsubRegistry&&(this._unsubRegistry(),this._unsubRegistry=null)}updated(e){e.has("hass")&&this.hass&&this._ensureRegistry()}shouldUpdate(e){if(e.size>1||!e.has("hass"))return!0;const t=[];for(const e of this._discoveredResult.list)t.push(...Object.values(e.entities));return 0===t.length||fe(e.get("hass"),this.hass,t)}willUpdate(e){this._config&&this.hass&&null!==this._registry&&(e.has("hass")||e.has("_registry")||e.has("_config"))&&(this._discoveredResult=this._listMemo(this.hass,this._refs,this._registry))}_ensureRegistry(){this._fetchRegistry(),this._unsubRegistry||(this._unsubRegistry=Vt(this.hass,()=>{this._fetchRegistry(!0)}))}_fetchRegistry(e=!1){this._fetchInFlight||(this._fetchInFlight=!0,Yt(this.hass,e).then(e=>{if(e!==this._registry&&(this._registry=e,this._registryError=null,this._config&&this.hass))for(const t of this._refs)Xt.set(bt(t),Kt(this.hass,t,e))}).catch(e=>{this._registryError=e?.message??"entity registry fetch failed"}).finally(()=>{this._fetchInFlight=!1}))}render(){if(!this._config||!this.hass)return Y;if(null===this._registry)return G`<ha-card>
        <div class="empty">
          <p class="dim">
            ${this._registryError?Ve("tile.registry_failed",{error:this._registryError}):Ve("root.loading_registry")}
          </p>
        </div>
      </ha-card>`;const{list:e,missing:t}=this._discoveredResult;if(0===e.length)return G`<ha-card>
        <div class="empty">
          <p><strong>${Ve("root.compass_no_match")}</strong></p>
          <p class="dim">
            ${Ve("root.compass_configured",{entries:this._refs.map(xt).join(", ")})}
          </p>
        </div>
      </ha-card>`;const o=this._config;return G`
      <ha-card>
        ${o.title?G`<div class="card-header">${o.title}</div>`:Y}
        <acp-sky-compass
          .hass=${this.hass}
          .discovered_list=${e}
          ?compact=${!!o.compact}
          .showLegend=${o.show_legend??!0}
          .showStats=${o.show_stats??!0}
          .showMoon=${o.show_moon??!1}
          .showCardinals=${o.show_cardinals??!0}
          .showBlindSpot=${o.show_blind_spot??!0}
          .showSunPath=${o.show_sun_path??!0}
          .showSunriseSunset=${o.show_sunrise_sunset??!0}
          .showCoverFill=${o.show_cover_fill??!0}
          .showWindowArrow=${o.show_window_arrow??!0}
          .coverColors=${o.cover_colors??[]}
          .northOffsetDeg=${st(o.north_offset??0)}
        ></acp-sky-compass>
        ${!1!==o.show_elevation_chart?G`<acp-elevation-chart
              .hass=${this.hass}
              .discoveredList=${e}
              .coverColors=${o.cover_colors??[]}
              ?compact=${!!o.compact}
            ></acp-elevation-chart>`:Y}
        ${t.length>0?G`<div class="warn dim">
              ${Ve("root.compass_not_found",{entries:t.map(xt).join(", ")})}
            </div>`:Y}
      </ha-card>
    `}};Ai.styles=r`
    :host {
      display: block;
    }
    ha-card {
      padding: 12px 14px 10px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      box-sizing: border-box;
    }
    .card-header {
      font-size: 1.05rem;
      font-weight: 500;
      color: var(--primary-text-color);
    }
    .empty {
      padding: 16px;
      text-align: center;
    }
    .dim {
      color: var(--secondary-text-color);
    }
    .warn {
      font-size: 0.78rem;
      text-align: center;
    }
  `,e([ge({attribute:!1})],Ai.prototype,"hass",void 0),e([me()],Ai.prototype,"_config",void 0),e([me()],Ai.prototype,"_registry",void 0),e([me()],Ai.prototype,"_registryError",void 0),Ai=e([he(we)],Ai),window.customCards=window.customCards||[],window.customCards.some(e=>e.type===we)||window.customCards.push({type:we,name:"Adaptive Cover — Sky Compass",description:"Polar sun-vs-FOV plot; overlay one or more Adaptive Cover entries on a single compass.",preview:!0,documentationURL:"https://github.com/mrvollger/adaptive-cover-card"});const Ci={compact:!1,hide_inactive_handlers:!1,show_decision_summary:!0},Ei={window:"editor.common.window",title:"editor.decision.title",compact:"editor.decision.compact_label",hide_inactive_handlers:"editor.decision.hide_inactive_handlers_label",show_decision_summary:"editor.decision.show_decision_summary_label"},Mi={compact:"editor.decision.compact_desc",hide_inactive_handlers:"editor.decision.hide_inactive_handlers_desc",show_decision_summary:"editor.decision.show_decision_summary_desc"};let zi=class extends ce{constructor(){super(...arguments),this._windows=null,this._windowsError=null,this._windowsFetchInFlight=!1,this._computeLabel=e=>{const t=Ei[e.name];return t?Ve(t):e.name},this._computeHelper=e=>{const t=Mi[e.name];return t?Ve(t):void 0},this._valueChanged=e=>{e.stopPropagation();const t={...e.detail.value};for(const[e,o]of Object.entries(Ci))this._config&&Object.prototype.hasOwnProperty.call(this._config,e)||t[e]!==o||delete t[e];const o=t.window;delete t.window;let i={...this._config??{type:""},...t};"string"==typeof o&&o&&o!==kt(this._config)&&(i=$t(i,o)),this._emit(i)}}setConfig(e){this._config={...e}}updated(e){e.has("hass")&&this.hass&&this._ensureWindows()}_ensureWindows(){this._windows||this._windowsFetchInFlight||(this._windowsFetchInFlight=!0,Qt(this.hass).then(e=>{this._windows=e,this._windowsError=null,this._config?.window||this._config?.entry_id||this._config?.cover||1!==e.length||this._emit($t(this._config??{type:""},e[0].window_key))}).catch(e=>{this._windowsError=e?.message??"failed to load windows"}).finally(()=>{this._windowsFetchInFlight=!1}))}_emit(e){this._config=e,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e},bubbles:!0,composed:!0}))}render(){if(!this._config)return Y;if(this._windowsError&&!this._windows)return G`
        <div class="form">
          <div class="error">${Ve("editor.common.load_failed",{error:this._windowsError})}</div>
          <label class="field-label" for="entry-id-fallback"
            >${Ve("editor.common.window_fallback_label")}</label
          >
          <input
            id="entry-id-fallback"
            type="text"
            class="text-input"
            .value=${kt(this._config)}
            placeholder=${Ve("editor.common.window_manual_placeholder")}
            @change=${e=>this._emit($t(this._config??{type:""},e.target.value))}
          />
          ${pi()}
        </div>
      `;const e=this._schema(),{entry_id:t,...o}=this._config,i=kt(this._config),s={...Ci,...o,...i?{window:i}:{}};return G`
      <div class="form">
        <ha-form
          .hass=${this.hass}
          .data=${s}
          .schema=${e}
          .computeLabel=${this._computeLabel}
          .computeHelper=${this._computeHelper}
          @value-changed=${this._valueChanged}
        ></ha-form>
        ${pi()}
      </div>
    `}_schema(){const e=(this._windows??[]).map(e=>({value:e.window_key,label:e.title})),t=kt(this._config);return t&&!e.some(e=>e.value===t)&&e.unshift({value:t,label:Ve("editor.common.unknown_entry",{entry:t})}),[{name:"window",required:!this._config?.cover,selector:{select:{options:e,mode:"dropdown"}}},{name:"title",selector:{text:{}}},{name:"compact",selector:{boolean:{}}},{name:"hide_inactive_handlers",selector:{boolean:{}}},{name:"show_decision_summary",selector:{boolean:{}}}]}};zi.styles=r`
    :host {
      display: block;
    }
    .form {
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding: 8px 0;
    }
    .field-label {
      font-weight: 500;
      font-size: 0.88rem;
      color: var(--primary-text-color);
    }
    .text-input {
      width: 100%;
      padding: 8px 10px;
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      background: var(--card-background-color, transparent);
      color: var(--primary-text-color);
      font-size: 0.9rem;
      font-family: inherit;
    }
    .error {
      font-size: 0.82rem;
      color: var(--error-color, crimson);
    }
    .version-footer {
      font-size: 0.7rem;
      text-align: right;
    }
    .dim {
      color: var(--secondary-text-color);
    }
  `,e([ge({attribute:!1})],zi.prototype,"hass",void 0),e([me()],zi.prototype,"_config",void 0),e([me()],zi.prototype,"_windows",void 0),e([me()],zi.prototype,"_windowsError",void 0),zi=e([he(Se)],zi);let Oi=class extends ce{constructor(){super(...arguments),this._registry=null,this._registryError=null,this._unsubRegistry=null,this._fetchInFlight=!1,this._fetchGen=0,this._memo=Bt(),this._discovered=null}setConfig(e){const t=yt(e);if(!t)throw new Error(`${ke}: set \`window\` (window key) or \`cover\` (cover entity); a legacy \`entry_id\` also works. It must be a non-empty string.`);if(this._config={...e},e.tooltips&&gt(e.tooltips),null===this._registry){const e=Xt.get(bt(t));e&&(this._registry=e.entries)}}getCardSize(){return 3}getGridOptions(){return{columns:12,rows:"auto",min_columns:4,max_columns:12}}static async getStubConfig(e){let t="";try{const o=await Qt(e);t=o[0]?.window_key??""}catch{}return{type:`custom:${ke}`,window:t}}static async getConfigElement(){return document.createElement(Se)}connectedCallback(){if(super.connectedCallback(),null===this._registry){const e=Lt();e&&(this._registry=e)}this.hass&&this._ensureRegistry()}disconnectedCallback(){super.disconnectedCallback(),this._unsubRegistry&&(this._unsubRegistry(),this._unsubRegistry=null)}updated(e){e.has("hass")&&this.hass&&this._ensureRegistry()}shouldUpdate(e){return e.size>1||!e.has("hass")||(!this._discovered||fe(e.get("hass"),this.hass,Object.values(this._discovered.entities)))}willUpdate(e){this._config&&this.hass&&null!==this._registry&&(e.has("hass")||e.has("_registry")||e.has("_config"))&&(this._discovered=this._memo(this.hass,this._config,this._registry))}_ensureRegistry(){this._fetchRegistry(),this._unsubRegistry||(this._unsubRegistry=Vt(this.hass,()=>{this._fetchRegistry(!0)}))}_fetchRegistry(e=!1){if(this._fetchInFlight)return;this._fetchInFlight=!0;const t=++this._fetchGen;Yt(this.hass,e).then(e=>{if(t!==this._fetchGen)return;if(e===this._registry)return;this._registry=e,this._registryError=null;const o=yt(this._config);o&&this.hass&&Xt.set(bt(o),Kt(this.hass,o,e))}).catch(e=>{t===this._fetchGen&&(this._registryError=e?.message??"entity registry fetch failed")}).finally(()=>{t===this._fetchGen&&(this._fetchInFlight=!1)})}render(){if(!this._config||!this.hass)return Y;if(null===this._registry)return G`<ha-card>
        <div class="empty">
          <p class="dim">
            ${this._registryError?Ve("tile.registry_failed",{error:this._registryError}):Ve("tile.loading")}
          </p>
        </div>
      </ha-card>`;const e=this._discovered;if(!e)return G`<ha-card>
        <div class="empty">
          <p class="dim">
            ${Ve("tile.entry_not_found",{entry:xt(yt(this._config))})}
          </p>
        </div>
      </ha-card>`;const t=this._config;return G`
      <ha-card>
        ${t.title?G`<div class="card-header">${t.title}</div>`:Y}
        <acp-decision-strip
          .hass=${this.hass}
          .discovered=${e}
          ?compact=${!!t.compact}
          ?hide-inactive=${!!t.hide_inactive_handlers||!!t.compact}
          .showSummary=${!1!==t.show_decision_summary}
        ></acp-decision-strip>
      </ha-card>
    `}};Oi.styles=r`
    :host {
      display: block;
    }
    ha-card {
      padding: 12px 14px 10px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      box-sizing: border-box;
    }
    .card-header {
      font-size: 1.05rem;
      font-weight: 500;
      color: var(--primary-text-color);
    }
    .empty {
      padding: 16px;
      text-align: center;
    }
    .dim {
      color: var(--secondary-text-color);
      margin: 0;
    }
  `,e([ge({attribute:!1})],Oi.prototype,"hass",void 0),e([me()],Oi.prototype,"_config",void 0),e([me()],Oi.prototype,"_registry",void 0),e([me()],Oi.prototype,"_registryError",void 0),Oi=e([he(ke)],Oi),window.customCards=window.customCards||[],window.customCards.some(e=>e.type===ke)||window.customCards.push({type:ke,name:"Adaptive Cover — Decision Strip",description:"Standalone decision strip: all pipeline handlers for one Adaptive Cover instance with the winning row highlighted.",preview:!0,documentationURL:"https://github.com/mrvollger/adaptive-cover-card"});const Ii=["hand","comfort","schedule","positions","glare","privacy"],Ti=["house","floor","area"],Fi=["house","area"],Ri=["house"],ji=[{key:"manual_override_duration",kind:"duration",levels:Fi,window:!1,section:"hand",unit:"min",min:1,max:1440,step:1,hub:"number"},{key:"manual_override_reset",kind:"bool",levels:Fi,window:!1,section:"hand"},{key:"manual_detection",kind:"bool",levels:Fi,window:!1,section:"hand",hub:"switch"},{key:"manual_ignore_intermediate",kind:"bool",levels:Fi,window:!1,section:"hand"},{key:"manual_threshold",kind:"number",levels:Fi,window:!1,section:"hand",unit:"%",min:0,max:99,step:1},{key:"climate_on",kind:"bool",levels:Fi,window:!1,section:"comfort",hub:"switch"},{key:"climate_mode",kind:"bool",levels:Fi,window:!1,section:"comfort"},{key:"temp_low",kind:"temperature",levels:Ti,window:!1,section:"comfort",hub:"number"},{key:"temp_high",kind:"temperature",levels:Ti,window:!1,section:"comfort",hub:"number"},{key:"temp_entity",kind:"entity",levels:["floor","area"],window:!1,section:"comfort",domains:["climate","sensor"]},{key:"use_outside_temp",kind:"bool",levels:Ri,window:!1,section:"comfort",hub:"switch"},{key:"use_lux",kind:"bool",levels:Ri,window:!1,section:"comfort",hub:"switch"},{key:"use_irradiance",kind:"bool",levels:Ri,window:!1,section:"comfort",hub:"switch"},{key:"start_time",kind:"time",levels:Fi,window:!1,section:"schedule"},{key:"start_entity",kind:"entity",levels:Fi,window:!1,section:"schedule",domains:["sensor","input_datetime"]},{key:"sunrise_offset",kind:"number",levels:Fi,window:!1,section:"schedule",unit:"min",step:1},{key:"end_time",kind:"time",levels:Fi,window:!1,section:"schedule"},{key:"end_entity",kind:"entity",levels:Fi,window:!1,section:"schedule",domains:["sensor","input_datetime"]},{key:"sunset_offset",kind:"number",levels:Fi,window:!1,section:"schedule",unit:"min",step:1,attr:"sunset_offset"},{key:"return_sunset",kind:"bool",levels:Fi,window:!1,section:"schedule"},{key:"default_percentage",kind:"number",levels:Fi,window:!0,section:"positions",unit:"%",min:0,max:100,step:1,attr:"default"},{key:"sunset_position",kind:"number",levels:Fi,window:!0,section:"positions",unit:"%",min:0,max:100,step:1,attr:"sunset_default"},{key:"eye_height",kind:"number",levels:Fi,window:!0,section:"glare",unit:"m",min:.1,max:3,step:.01,hub:"number"},{key:"occupied_distance",kind:"number",levels:Fi,window:!0,section:"glare",unit:"m",min:.1,max:10,step:.1,hub:"number"},{key:"privacy_offset",kind:"number",levels:Fi,window:!1,section:"privacy",unit:"min",min:0,max:180,step:5,hub:"number"},{key:"privacy_position",kind:"number",levels:Fi,window:!1,section:"privacy",unit:"%",min:0,max:100,step:1}],Ni=new Map(ji.map(e=>[e.key,e])),Pi=["climate_on","temp_low","temp_high","manual_override_duration","eye_height","occupied_distance"];function Di(e){const t=e?.config?.unit_system?.temperature;return"string"==typeof t&&t?t:"°C"}function Ki(e,t){const o="°F"===t;return"temp_high"===e?o?{min:50,max:100,step:.5}:{min:10,max:40,step:.5}:o?{min:40,max:90,step:.5}:{min:5,max:30,step:.5}}function Bi(e,t){if("temperature"===t.kind){const o=Di(e);return{...Ki(t.key,o),unit:o}}return{min:t.min,max:t.max,step:t.step,unit:t.unit}}function Wi(e,t){if(null==t||""===t)return null;switch(e.kind){case"bool":return"boolean"==typeof t?t:"on"===t||"true"===t||"off"!==t&&"false"!==t&&null;case"duration":return function(e){if("number"==typeof e)return Number.isFinite(e)?e:null;if("string"==typeof e){const t=parseFloat(e);return Number.isFinite(t)?t:null}if(!e||"object"!=typeof e)return null;const t=e,o=e=>"number"==typeof e&&Number.isFinite(e)?e:Number(e)||0;return 60*o(t.hours)+o(t.minutes)+o(t.seconds)/60}(t);case"number":case"temperature":{const e="number"==typeof t?t:parseFloat(String(t));return Number.isFinite(e)?e:null}case"time":{const e=/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(String(t));return e?`${e[1].padStart(2,"0")}:${e[2]}:${e[3]??"00"}`:null}case"entity":return"string"==typeof t?t:null}}function Vi(e){return String(Math.round(100*e)/100)}function Gi(e,t,o){if(null==o)return"entity"===t.kind||"time"===t.kind?Ve("settings.value.none"):Ve("settings.value.unset");switch(t.kind){case"bool":return Ve(o?"settings.value.on":"settings.value.off");case"duration":return"number"==typeof o?function(e){const t=Math.round(e),o=Math.floor(t/60),i=t%60;return o>0&&i>0?Ve("settings.value.hours_minutes",{h:o,m:i}):o>0?Ve("settings.value.hours",{h:o}):Ve("settings.value.minutes",{m:i})}(o):String(o);case"temperature":return"number"==typeof o?`${Vi(o)} ${Di(e)}`:String(o);case"number":return"number"!=typeof o?String(o):"sunrise_offset"===t.key||"sunset_offset"===t.key?function(e,t){const o="sunrise_offset"===t?"sunrise":"sunset";return 0===e?Ve(`settings.value.at_${o}`):Ve(e<0?`settings.value.before_${o}`:`settings.value.after_${o}`,{n:Vi(Math.abs(e))})}(o,t.key):"%"===t.unit?`${Vi(o)}%`:"min"===t.unit?Ve("settings.value.minutes",{m:Vi(o)}):t.unit?`${Vi(o)} ${t.unit}`:Vi(o);case"time":{const e=String(o);return"00:00:00"===e?Ve("settings.value.midnight"):e.slice(0,5)}case"entity":{const t=String(o),i=e?.states?.[t]?.attributes?.friendly_name;return"string"==typeof i&&i?i:t}}}function Ui(e){const t=Ve(`settings.label.${e}`);if(t!==`settings.label.${e}`)return t;const o=e.replace(/_/g," ");return o.charAt(0).toUpperCase()+o.slice(1)}const Li=/^[a-z_]+\.[a-z0-9_]+$/;let Yi=class extends ce{constructor(){super(...arguments),this.rows=[],this.windows=[],this.busy=!1,this._drafts={}}willUpdate(e){const t=e.get("scope");!t||t.level===this.scope?.level&&t.id===this.scope?.id||(this._drafts={})}_emit(e,t){this.dispatchEvent(new CustomEvent(e,{detail:t,bubbles:!0,composed:!0}))}_set(e,t){const o={...this._drafts};delete o[e],this._drafts=o,this._emit("acp-setting-set",{key:e,value:t})}_levelWord(){return Ve(`settings.level.${this.scope.level}`)}_effective(e){return"house"===this.scope.level||e.own?e.value:e.inherited?.value}render(){const e=Ii.map(e=>({section:e,rows:this.rows.filter(t=>t.setting.section===e)})).filter(e=>e.rows.length>0);return G`${this.windows.length>0?this._renderWindows():Y}
    ${e.map(e=>G`<section class="section" data-section=${e.section}>
          <h3 class="eyebrow">${Ve(`settings.section.${e.section}`)}</h3>
          ${e.rows.map(e=>this._renderRow(e))}
        </section>`)}`}_renderWindows(){return G`<section class="windows">
      <h3 class="eyebrow">${Ve("settings.window_exceptions")}</h3>
      <p class="muted small">${Ve("settings.window_exceptions_hint")}</p>
      ${this.windows.map(e=>G`<button
            type="button"
            class="win"
            data-window=${e.window.key}
            @click=${()=>this._emit("acp-open-window",{key:e.window.key})}
          >
            <span class="strong">${e.window.deviceName}</span>
            <span class="muted small"
              >${e.settings.map(e=>e.legacy?Ve("settings.legacy_setting",{name:Ui(e.key)}):Ui(e.key)).join(", ")}</span
            >
          </button>`)}
    </section>`}_stateText(e){if("house"===this.scope.level)return Y;const t=e.setting,o=this._levelWord();let i,s;if(!0===e.own)s="own",i=void 0===e.value?Ve("settings.state.own_unknown",{level:o}):Ve("settings.state.own",{level:o,value:Gi(this.hass,t,e.value)});else if(!1===e.own&&e.inherited){s="inherit";const o="floor"===e.inherited.level?Ve("settings.state.from_floor",{floor:e.inherited.name??""}):Ve("settings.state.from_house");i=void 0===e.inherited.value?o:`${o}: ${Gi(this.hass,t,e.inherited.value)}`}else s="unknown",i=Ve("settings.state.unknown");return G`<span class="state ${s}">${i}</span>`}_houseText(e){if("house"===this.scope.level)return Y;const t=e.setting,o=t.levels.includes("house")?void 0===e.houseValue?Ve("settings.house_unknown"):Ve("settings.house_value",{value:Gi(this.hass,t,e.houseValue)}):Ve("settings.house_per_floor");return G`<span class="house muted small">${o}</span>`}_renderRow(e){const t=e.setting,o=function(e){const t=Ve(`settings.hint.${e}`);return t===`settings.hint.${e}`?null:t}(t.key),i="house"!==this.scope.level&&!0===e.own,s="floor"===e.inherited?.level?Ve("settings.reset_floor",{floor:e.inherited.name??""}):Ve("settings.reset");return G`<div class="row ${!0===e.own?"is-own":""}" data-key=${t.key}>
      <div class="row-head">
        <span class="label">
          <span class="strong">${Ui(t.key)}</span>
          ${o?G`<span class="muted small">${o}</span>`:Y}
        </span>
        ${this._stateText(e)}
      </div>
      ${this._houseText(e)}
      <div class="edit">
        ${this._renderEditor(e)}
        ${i?G`<button
              type="button"
              class="btn reset"
              ?disabled=${this.busy}
              @click=${()=>this._emit("acp-setting-reset",{key:t.key})}
            >
              ${s}
            </button>`:Y}
      </div>
      ${this._renderExceptions(e)}
    </div>`}_renderExceptions(e){return 0===e.exceptions.length?Y:G`<div class="exceptions" aria-label=${Ve("settings.exceptions")}>
      ${e.exceptions.map(t=>{const o=void 0===t.value?"":` · ${Gi(this.hass,e.setting,t.value)}`,i=t.legacy?` ${Ve("settings.legacy_mark")}`:"";return G`<span class="exc ${t.level}" data-level=${t.level} data-id=${t.id}
          >${t.name}${o}${i}</span
        >`})}
    </div>`}_renderEditor(e){const t=e.setting,o=this._effective(e);if("bool"===t.kind){const i=!0===o?"on":!1===o?"off":null;return G`<div class="seg" role="group" aria-label=${Ui(t.key)}>
        ${["on","off"].map(o=>{const s=i===o;return G`<button
            type="button"
            class="seg-btn ${s?"on":""}"
            data-value=${o}
            aria-pressed=${s?"true":"false"}
            ?disabled=${this.busy}
            @click=${()=>{const i="on"===o;s&&("house"===this.scope.level||e.own)||this._set(t.key,i)}}
          >
            ${Ve(`settings.value.${o}`)}
          </button>`})}
      </div>`}const i=this._drafts[t.key],s=i??(null==o?"":this._inputText(t,o)),n=void 0===i?void 0:this._parse(t,i),r=null!=n,a=r&&("house"===this.scope.level||e.own)&&function(e,t){return"number"==typeof e&&"number"==typeof t?Math.abs(e-t)<1e-9:e===t}(n,e.value),l=!this.busy&&r&&!a,c=!this.busy&&void 0===i&&"house"!==this.scope.level&&!e.own,d=()=>{l?this._set(t.key,n):c&&null!=o&&this._set(t.key,o)},h=l||c&&null!=o,u=e=>{this._drafts={...this._drafts,[t.key]:e.target.value}},p=e=>{"Enter"===e.key&&d()};let g;if("time"===t.kind)g=G`<input
        type="time"
        class="input"
        aria-label=${Ui(t.key)}
        .value=${s}
        ?disabled=${this.busy}
        @input=${u}
        @keydown=${p}
      />`;else if("entity"===t.kind){const e=`acp-entities-${t.key}`;g=G`<input
          type="text"
          class="input entity"
          list=${e}
          aria-label=${Ui(t.key)}
          placeholder=${(t.domains??[]).map(e=>`${e}.…`).join(" / ")}
          .value=${s}
          ?disabled=${this.busy}
          @input=${u}
          @keydown=${p}
        />
        <datalist id=${e}>
          ${this._entityOptions(t).map(e=>G`<option value=${e}></option>`)}
        </datalist>`}else{const e=Bi(this.hass,t);g=G`<span class="num">
        <input
          type="number"
          class="input"
          aria-label=${Ui(t.key)}
          min=${e.min??Y}
          max=${e.max??Y}
          step=${e.step??"any"}
          .value=${s}
          ?disabled=${this.busy}
          @input=${u}
          @keydown=${p}
        />
        ${e.unit?G`<span class="unit muted">${e.unit}</span>`:Y}
      </span>`}const m="house"===this.scope.level?Ve("settings.save"):Ve("settings.save_here",{level:this._levelWord()});return G`${g}
      <button type="button" class="btn save" ?disabled=${!h} @click=${d}>
        ${m}
      </button>`}_inputText(e,t){return"time"===e.kind?String(t).slice(0,5):String("number"==typeof t?Math.round(100*t)/100:t)}_parse(e,t){const o=t.trim();if("entity"===e.kind)return Li.test(o)?o:null;const i=Wi(e,o);if("number"==typeof i){const t=Bi(this.hass,e);if(void 0!==t.min&&i<t.min)return null;if(void 0!==t.max&&i>t.max)return null}return i}_entityOptions(e){const t=new Set(e.domains??[]);return Object.keys(this.hass?.states??{}).filter(e=>t.has(e.slice(0,e.indexOf(".")))).sort()}};Yi.styles=r`
    :host {
      display: flex;
      flex-direction: column;
      gap: 18px;
      color: var(--primary-text-color);
    }
    .eyebrow {
      margin: 0 0 4px;
      font-size: 0.8rem;
      font-weight: 700;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.6px;
    }
    .muted {
      color: var(--secondary-text-color);
    }
    .small {
      font-size: 0.85rem;
    }
    .strong {
      font-weight: 600;
    }
    .section,
    .windows {
      display: flex;
      flex-direction: column;
      gap: 0;
    }
    .windows p {
      margin: 0 0 6px;
    }
    .win {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 2px;
      padding: 10px 0;
      border: none;
      border-bottom: 1px solid var(--acp-line, var(--divider-color));
      background: transparent;
      color: var(--primary-text-color);
      font: inherit;
      text-align: left;
      cursor: pointer;
    }
    .row {
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: 12px 0;
      border-bottom: 1px solid var(--acp-line, var(--divider-color));
    }
    .row-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 10px;
    }
    .label {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }
    .state {
      flex-shrink: 0;
      max-width: 55%;
      text-align: right;
      font-size: 0.8rem;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 999px;
      background: var(--acp-track, #efefef);
    }
    .state.own {
      color: var(--primary-text-color);
      background: rgba(255, 166, 0, 0.3);
      background: color-mix(in srgb, var(--acp-hold, #ffa600) 30%, transparent);
    }
    .state.inherit,
    .state.unknown {
      font-weight: 600;
      color: var(--secondary-text-color);
    }
    .edit {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
    }
    .num {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .input {
      box-sizing: border-box;
      min-height: 40px;
      width: 110px;
      padding: 0 10px;
      border: 1px solid var(--acp-line, var(--divider-color));
      border-radius: 10px;
      background: var(--acp-surface, var(--card-background-color));
      color: var(--primary-text-color);
      font: inherit;
    }
    .input.entity {
      width: 240px;
      max-width: 100%;
    }
    .btn {
      min-height: 40px;
      padding: 0 14px;
      border: 1px solid var(--acp-line, var(--divider-color));
      border-radius: 10px;
      background: var(--acp-surface, var(--card-background-color));
      color: var(--primary-text-color);
      font: inherit;
      font-weight: 600;
      cursor: pointer;
    }
    .btn[disabled] {
      cursor: default;
      opacity: 0.5;
    }
    .btn.reset {
      border-style: dashed;
    }
    .seg {
      display: inline-flex;
      gap: 3px;
      padding: 3px;
      border-radius: 10px;
      background: var(--acp-track, #efefef);
    }
    .seg-btn {
      min-height: 36px;
      padding: 0 16px;
      border: none;
      border-radius: 8px;
      background: transparent;
      color: var(--primary-text-color);
      font: inherit;
      font-weight: 600;
      cursor: pointer;
    }
    .seg-btn.on {
      background: var(--acp-auto, var(--primary-color));
      color: var(--acp-on-auto, #fff);
    }
    .exceptions {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .exc {
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 600;
      background: var(--acp-track, #efefef);
    }
    .exc.area {
      background: rgba(255, 166, 0, 0.22);
      background: color-mix(in srgb, var(--acp-hold, #ffa600) 22%, transparent);
    }
    .exc.floor {
      background: rgba(3, 169, 244, 0.16);
      background: color-mix(in srgb, var(--acp-auto, #03a9f4) 16%, transparent);
    }
    button:focus-visible,
    input:focus-visible {
      outline: 3px solid var(--acp-auto, var(--primary-color));
      outline-offset: 2px;
    }
  `,e([ge({attribute:!1})],Yi.prototype,"hass",void 0),e([ge({attribute:!1})],Yi.prototype,"scope",void 0),e([ge({attribute:!1})],Yi.prototype,"rows",void 0),e([ge({attribute:!1})],Yi.prototype,"windows",void 0),e([ge({type:Boolean})],Yi.prototype,"busy",void 0),e([me()],Yi.prototype,"_drafts",void 0),Yi=e([he("acp-settings-sheet")],Yi);const Hi={"sensor:target_position":"position","select:mode":"mode","button:return_to_auto":"returnButton","binary_sensor:manual_override":"manualOverride","binary_sensor:sun_motion":"sunInFront","sensor:control":"controlMethod","switch:control_toggle":"controlSwitch","switch:switch_mode":"climateSwitch"},Qi={"sensor:Cover Position":"position","select:mode_select":"mode","button:Reset Manual Override":"returnButton","binary_sensor:Manual Override":"manualOverride","binary_sensor:Sun Infront":"sunInFront","sensor:Control Method":"controlMethod","switch:Toggle Control":"controlSwitch","switch:Climate Mode":"climateSwitch"},qi=Object.fromEntries(Object.entries(Qi).map(([e,t])=>[t,e.slice(e.indexOf(":")+1)])),Xi={"switch:climate_on":"climate_on","switch:manual_detection":"manual_detection","switch:use_outside_temp":"use_outside_temp","switch:use_lux":"use_lux","switch:use_irradiance":"use_irradiance","number:temp_low":"temp_low","number:temp_high":"temp_high","number:manual_override_duration":"manual_override_duration","number:eye_height":"eye_height","number:occupied_distance":"occupied_distance","number:privacy_offset":"privacy_offset"},Ji={"select:house_mode":"modeSelect","button:return_all_to_auto":"returnButton","switch:climate_on":"climateSwitch"},Zi="adaptive_cover_hub_",es={"cover:cover":"cover","select:house_mode":"modeSelect","button:reset_all":"returnButton","switch:climate_on":"climateSwitch"};function ts(e){return"string"==typeof e&&e.length>0}function os(e){return e.slice(0,e.indexOf("."))}const is=new WeakMap,ss=new WeakMap;function ns(e,t){if(!ts(e))return;const o=`_${qi[t]}`;return e.length>o.length&&e.endsWith(o)?e.slice(0,-o.length):void 0}function rs(e,t){const o=os(e.entity_id),i=t?.unique_id;if("cover"===o)return{row:e,hub:"cover",reg:t};const s=e.translation_key??t?.translation_key;if(ts(s)){const n=Xi[`${o}:${s}`],r=Ji[`${o}:${s}`];if(r)return{row:e,hub:r,hubSetting:n,reg:t};const a=Hi[`${o}:${s}`];return a?{row:e,window:a,uidKey:ns(i,a),reg:t}:n?{row:e,hubSetting:n,reg:t}:null}if(!ts(i))return null;if(i.startsWith(Zi)){const s=`${o}:${i.slice(19)}`,n=es[s],r=Xi[s];return n||r?{row:e,hub:n,hubSetting:r,reg:t}:null}for(const[s,n]of Object.entries(Qi)){if(!s.startsWith(`${o}:`))continue;const r=ns(i,n);if(r)return{row:e,window:n,uidKey:r,reg:t}}return null}function as(e,t){return e.states[t]?.attributes}function ls(e){const t=[];return ts(e?.cover_entity)&&t.push(e.cover_entity),Array.isArray(e?.cover_entities)&&t.push(...e.cover_entities.filter(ts)),0===t.length&&(t.push(...Object.keys(e?.last_moves??{}),...Object.keys(e?.move_blocked_by??{})),t.sort()),[...new Set(t)]}const cs=new Set(["cover_blind","cover_awning","cover_tilt"]);function ds(e,t){const o=e.entities?.[t];if(!o)return null;if(ts(o.area_id))return o.area_id;const i=o.device_id?e.devices?.[o.device_id]:void 0;return ts(i?.area_id)?i.area_id:null}function hs(e,t){return!(!ts(t)||e.areas&&!e.areas[t])}function us(e,t){if(!t)return e;const o=e.toLowerCase(),i=t.toLowerCase();if(!o.startsWith(i)||e.length<=t.length)return e;const s=e.slice(t.length);if(!/^[\s\-–—:·]/.test(s))return e;const n=s.replace(/^[\s\-–—:·]+/,"");return n?n.charAt(0).toUpperCase()+n.slice(1):e}const ps=(e,t)=>e.name.localeCompare(t.name,void 0,{numeric:!0,sensitivity:"base"});function gs(e,t,o={}){const i=e,s=t,n=function(e){if(!e)return null;let t=ss.get(e);return t||(t=new Map(e.map(e=>[e.entity_id,e])),ss.set(e,t)),t}(s);let r=!1;const a=[];for(const e of function(e,t){const o=e.entities;if(o){const e=is.get(o);if(e)return e;const t=Object.values(o).filter(e=>e?.platform===Me);return is.set(o,t),t}return(t??[]).filter(e=>e.platform===Me).map(e=>({entity_id:e.entity_id,platform:e.platform,device_id:e.device_id,area_id:e.area_id??null,translation_key:e.translation_key??null,hidden:!!e.hidden_by,disabled_by:e.disabled_by??null}))}(i,s)){const t=n?.get(e.entity_id);if(e.disabled_by||t?.disabled_by)continue;const o=rs(e,t);(e.hidden||t?.hidden_by)&&"climateSwitch"!==o?.window||(o?a.push(o):ts(e.translation_key)||t||"number"===os(e.entity_id)||(r=!0))}const l={};let c=null;for(const e of a)e.hub&&!l[e.hub]&&(l[e.hub]=e.row.entity_id),e.hub&&!c&&ts(e.row.device_id)&&(c=e.row.device_id);const d={};for(const e of a)e.hubSetting&&!d[e.hubSetting]&&(null!==c&&e.row.device_id===c||e.reg?.unique_id?.startsWith(Zi))&&(d[e.hubSetting]=e.row.entity_id);const h=[],u=new Map,p=new Map,g=new Set;for(const t of a){if("position"!==t.window)continue;const o=as(e,t.row.entity_id)?.window_key,i=ts(o)?o:t.uidKey??t.row.device_id??t.row.entity_id;if(g.has(i))continue;g.add(i);const s={key:i,uidKey:t.uidKey,position:t,entities:{position:t.row.entity_id}};h.push(s),t.uidKey&&u.set(t.uidKey,s),ts(o)&&u.set(o,u.get(o)??s),t.row.device_id&&!p.has(t.row.device_id)&&p.set(t.row.device_id,s)}for(const e of a){if(!e.window||"position"===e.window)continue;const t=(e.uidKey?u.get(e.uidKey):void 0)??(e.row.device_id?p.get(e.row.device_id):void 0);t&&!t.entities[e.window]&&(t.entities[e.window]=e.row.entity_id)}const m=new Set(o.floors??[]),f=new Set(o.areas??[]),_=m.size>0||f.size>0,v=[];for(const t of h){const o=t.position.row.entity_id,s=as(e,o),n=ls(s),r=t.position.row.device_id??null,a=r?i.devices?.[r]:void 0,l=e.states[o]?.attributes?.friendly_name,c=a?.name_by_user||a?.name||(ts(l)?l:t.key),d=[t.position.row.area_id,a?.area_id,...n.map(e=>ds(i,e))],h=d.find(e=>hs(i,e))??null,u=h?i.areas?.[h]:void 0,p=ts(u?.floor_id)&&i.floors?.[u.floor_id]?u.floor_id:null;if(_&&(!p||!m.has(p))&&(!h||!f.has(h)))continue;const g=s?.cover_type;v.push({key:t.key,name:us(c,u?.name),deviceName:c,deviceId:r,areaId:h,floorId:p,coverType:ts(g)&&cs.has(g)?g:"cover_blind",covers:n,entities:t.entities,configEntryId:t.position.reg?.config_entry_id??null,configSubentryId:t.position.reg?.config_subentry_id??null})}const y=new Map,w=new Map;for(const e of v){let t=y.get(e.floorId);if(!t){const o=e.floorId?i.floors?.[e.floorId]:void 0;t={id:e.floorId,name:o?.name??"Other",level:"number"==typeof o?.level?o.level:null,rooms:[]},y.set(e.floorId,t)}const o=`${e.floorId??""}|${e.areaId??""}`;let s=w.get(o);s||(s={id:e.areaId,name:e.areaId?i.areas?.[e.areaId]?.name??e.areaId:"Unassigned",windows:[]},w.set(o,s),t.rooms.push(s)),s.windows.push(e)}const b=[...y.values()];b.sort((e,t)=>null===e.id!=(null===t.id)?null===e.id?1:-1:null===e.level!=(null===t.level)?null===e.level?1:-1:null!==e.level&&null!==t.level&&e.level!==t.level?t.level-e.level:ps(e,t));for(const e of b){e.rooms.sort((e,t)=>null===e.id!=(null===t.id)?null===e.id?1:-1:ps(e,t));for(const t of e.rooms)t.windows.sort(ps)}1===b.length&&null===b[0].id&&(b[0].name="");const x=b.flatMap(e=>e.rooms.flatMap(e=>e.windows));return{floors:b,windows:x,hub:l,hubSettings:d,hubDeviceId:c,needsRegistry:r&&!t}}const ms=/^(manual|off)$/i,fs=/^hold$/i,_s=/^(auto|adaptive)$/i,vs=/climate/i;function ys(e,t){return t?e.states[t]?.state:void 0}function ws(e,t){const o=t?e.states[t]?.attributes?.options:void 0;return Array.isArray(o)?o.filter(e=>"string"==typeof e):[]}function bs(e){return e.find(e=>ms.test(e))}function xs(e){return e.find(e=>fs.test(e))}function $s(e,t){const o=e.find(e=>_s.test(e));if(o)return o;const i=e.filter(e=>!ms.test(e)&&!fs.test(e));if(t){const e=i.find(e=>vs.test(e));if(e)return e}return i.find(e=>!vs.test(e))??i[0]}function ks(e,t){const o=ys(e,t.entities.climateSwitch);return void 0===o||"on"===o}function Ss(e,t){const o=ys(e,t.entities.mode);return o&&ms.test(o)||"off"===ys(e,t.entities.controlSwitch)?"off":o&&fs.test(o)||"on"===ys(e,t.entities.manualOverride)?"hold":"auto"}function As(e){return 0===e.length?null:e.every(t=>t===e[0])?e[0]:"mixed"}function Cs(e){const t="number"==typeof e?e:parseFloat(String(e??""));return Number.isFinite(t)?t:null}function Es(e,t){const o=t.entities.position,i=o?e.states[o]:void 0,s=i?.attributes??{},n=Ss(e,t),r=!!i&&"unavailable"!==i.state&&"unknown"!==i.state,a=r?Cs(i.state):null,l=t.covers.length>0?no(e,t.coverType,t.covers[0]):null;let c=null;"hold"===n&&(c=[t.entities.mode?e.states[t.entities.mode]?.attributes?.until:void 0,t.entities.manualOverride?e.states[t.entities.manualOverride]?.attributes?.until:void 0,s.override_until].find(e=>"string"==typeof e&&e.length>0)??null);const d=t.entities.sunInFront,h=d?"on"===e.states[d]?.state:!0===s.sun?.in_fov,u=s.next_move;return{mode:n,holdUntil:c,position:l??a,target:a,sunOnGlass:h,nextMove:u&&"string"==typeof u.time&&u.time?{time:u.time,position:Cs(u.position)}:null,intent:"string"==typeof s.intent?s.intent:null,trace:Array.isArray(s.decision_trace)?s.decision_trace.filter(e=>"string"==typeof e):[],azimuth:Cs(s.azimuth_window??s.sun?.window_azimuth),available:r}}function Ms(e){return!!xs(e)&&e.some(e=>_s.test(e))}function zs(e,t){return t.length>0&&t.every(t=>!!xs(ws(e,t.entities.mode)))}function Os(e,t){const o=new Map;for(const{key:t,id:i}of e){const e=o.get(t)??[];e.includes(i)||e.push(i),o.set(t,e)}return[...o.entries()].map(([e,o])=>t(e,o))}const Is=(e,t)=>({domain:"select",service:"select_option",data:{entity_id:t,option:e}}),Ts=(e,t,o)=>({domain:e,service:t,data:{entity_id:o}});function Fs(e,t,o){const i=[],s=[];for(const n of t){const t=ws(e,n.entities.mode),r=o?$s(t,ks(e,n)):bs(t);n.entities.mode&&r?i.push({key:r,id:n.entities.mode}):n.entities.controlSwitch&&s.push(n.entities.controlSwitch)}const n=Os(i,(e,t)=>Is(e,t));return s.length>0&&n.push(Ts("switch",o?"turn_on":"turn_off",s)),n}function Rs(e,t,o){const i=new Map(t.map(t=>[t,Ss(e,t)])),s=t.filter(e=>i.get(e)!==o);if(0===s.length)return[];if("off"===o)return Fs(e,s,!1);if("hold"===o)return js(e,s);const n=s.filter(t=>Ms(ws(e,t.entities.mode))),r=Os(n.map(t=>({key:$s(ws(e,t.entities.mode),!1),id:t.entities.mode})),(e,t)=>Is(e,t)),a=s.filter(e=>!n.includes(e));r.push(...Fs(e,a.filter(e=>"off"===i.get(e)),!0));const l=a.map(e=>e.entities.returnButton).filter(e=>!!e);return l.length>0&&r.push(Ts("button","press",l)),r}function js(e,t,o){const i=t.filter(t=>!!xs(ws(e,t.entities.mode))).map(e=>e.entities.mode);if(0===i.length)return[];const s={entity_id:[...new Set(i)]};return void 0!==o&&(s.duration=function(e){const t=Math.max(0,Math.round(e/1e3));return{hours:Math.floor(t/3600),minutes:Math.floor(t%3600/60),seconds:t%60}}(o)),[{domain:Me,service:"hold",data:s}]}function Ns(e,t){const{hub:o,windows:i,useHub:s}=t;if(!s)return Rs(e,i,"auto");const n=ws(e,o.modeSelect);if(o.modeSelect&&Ms(n))return[Is($s(n,!1),[o.modeSelect])];const r=[],a=i.some(t=>"off"===Ss(e,t));if(a){const t=o.modeSelect?$s(ws(e,o.modeSelect),!1):void 0;o.modeSelect&&t?r.push(Is(t,[o.modeSelect])):r.push(...Fs(e,i.filter(t=>"off"===Ss(e,t)),!0))}if(o.returnButton)r.push(Ts("button","press",[o.returnButton]));else{const e=i.map(e=>e.entities.returnButton).filter(e=>!!e);e.length>0&&r.push(Ts("button","press",e))}return r}const Ps={open:["open_cover","open_cover_tilt"],close:["close_cover","close_cover_tilt"],stop:["stop_cover","stop_cover_tilt"]};function Ds(e,t){const[o,i]=Ps[t],s=e.flatMap(e=>e.covers.map(t=>({key:"cover_tilt"===e.coverType?i:o,id:t})));return Os(s,(e,t)=>Ts("cover",e,t))}function Ks(e,t){return e.useHub&&e.hub.cover?[Ts("cover",Ps[t][0],[e.hub.cover])]:Ds(e.windows,t)}function Bs(e,t){const o=t?.useHub?t.hub.climateSwitch:void 0,i=ys(e,o);return!o||"on"!==i&&"off"!==i?null:o}function Ws(e){return e.locale??{}}function Vs(e){if("local"===Ws(e).time_zone)return;const t=e.config?.time_zone;return t||void 0}function Gs(e,t){if(!t)return"";const o=new Date(t);if(Number.isNaN(o.getTime()))return"";const i=Ws(e),s={hour:"numeric",minute:"2-digit",hour12:"12"===i.time_format||"24"!==i.time_format&&void 0},n=i.language||e.language||"en";try{return o.toLocaleTimeString(n,{...s,timeZone:Vs(e)})}catch{return o.toLocaleTimeString(void 0,s)}}function Us(e,t){if(!e)return null;const o=Date.parse(e);if(Number.isNaN(o))return null;const i=Math.ceil((o-t)/6e4);if(i<1)return Ve("house.left_under_minute");const s=Math.floor(i/60),n=i%60;return s>0?`${s}h ${n}m`:`${n}m`}const Ls=["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];function Ys(e){const t=Math.round((e%360+360)%360/22.5)%16;return Ls[t]}function Hs(e,t){return Ve(`house.count.${e}_${1===t?"one":"other"}`,{n:t})}function Qs(e){return null===e?"—":`${Math.round(e)}%`}function qs(e){return Qs(e.position)}function Xs(e,t,o){if(!t.available)return Ve("house.next.unavailable");if("off"===t.mode)return Ve("house.next.off");if("hold"===t.mode){const e=Us(t.holdUntil,o);return e?Ve("house.next.hold",{left:e}):Ve("house.next.hold_unknown")}if(t.nextMove){const o=Gs(e,t.nextMove.time);if(o&&null!==t.nextMove.position)return Ve("house.next.move",{position:Qs(t.nextMove.position),time:o});if(o)return Ve("house.next.change",{time:o})}return Ve("house.next.none")}function Js(e,t){if("hold"===e.mode){const o=Us(e.holdUntil,t);return o?Ve("house.chip_hold_left",{left:o}):Ve("house.mode.hold")}return Ve(`house.mode.${e.mode}`)}const Zs=new Set(["legacy","window","area","floor"]);function en(e,t){const o=t.entities.position;return o?e.states[o]?.attributes:void 0}function tn(e,t){const o=en(e,t)?.provenance;if(!o||"object"!=typeof o||Array.isArray(o))return null;const i={};for(const[e,t]of Object.entries(o))"string"==typeof t&&Zs.has(t)&&(i[e]=t);return i}function on(e,t,o){if(!o.attr)return;const i=en(e,t);if(!i||!(o.attr in i))return;const s=Wi(o,i[o.attr]);return null===s?void 0:s}function sn(e,t){return!!e&&Object.prototype.hasOwnProperty.call(e,t)}class nn{constructor(e,t,o){this.hass=e,this.model=t,this.stored=o,this.infos=t.windows.map(t=>({w:t,prov:tn(e,t)}))}windowsIn(e,t){return"house"===e?this.infos:this.infos.filter(o=>("area"===e?o.w.areaId:o.w.floorId)===t)}bucket(e,t){if(this.stored)return("floor"===e?this.stored.floors:this.stored.areas)[t]??{}}valueFrom(e,t,o){for(const i of e){if(i.prov?.[t.key]!==o)continue;const e=on(this.hass,i.w,t);if(void 0!==e)return e}}houseValue(e){if(!e.levels.includes("house"))return;const t=function(e,t,o){const i=t.hubSettings?.[o.key],s=i?e.states[i]:void 0;if(!s||"unavailable"===s.state||"unknown"===s.state)return;const n=Wi(o,s.state);return null===n?void 0:n}(this.hass,this.model,e);if(void 0!==t)return t;if(this.stored&&sn(this.stored.house,e.key))return Wi(e,this.stored.house[e.key]);for(const t of this.infos){if(!t.prov||e.key in t.prov)continue;const o=on(this.hass,t.w,e);if(void 0!==o)return o}}own(e,t,o){const i=this.bucket(e,t);if(i)return sn(i,o.key)?{own:!0,value:Wi(o,i[o.key])}:{own:!1,value:void 0};const s=this.windowsIn(e,t).filter(e=>null!==e.prov);return s.some(t=>t.prov[o.key]===e)?{own:!0,value:this.valueFrom(s,o,e)}:s.some(t=>(t=>void 0===t||"area"===e&&"floor"===t)(t.prov[o.key]))?{own:!1,value:void 0}:{own:null,value:void 0}}exceptions(e,t){const o=[],i=this.windowsIn(e.level,e.id);if("house"===e.level&&t.levels.includes("floor"))for(const e of this.model.floors){if(null===e.id)continue;const i=this.own("floor",e.id,t);i.own&&o.push({level:"floor",id:e.id,name:e.name,value:i.value})}if("area"!==e.level&&t.levels.includes("area"))for(const i of this.model.floors)if("floor"!==e.level||i.id===e.id)for(const e of i.rooms){if(null===e.id)continue;const i=this.own("area",e.id,t);i.own&&o.push({level:"area",id:e.id,name:e.name,value:i.value})}for(const e of i){const i=e.prov?.[t.key];"window"!==i&&"legacy"!==i||o.push({level:"window",id:e.w.key,name:e.w.deviceName,value:on(this.hass,e.w,t),legacy:"legacy"===i})}return o}}function rn(e,t,o){const i=Ni.get(t),s={scope:e.level};return"house"!==e.level&&(s.id=e.id),s[t]=i?function(e,t){return null===t?null:"duration"===e.kind&&"number"==typeof t?function(e){const t=Math.max(0,Math.round(60*e));return{hours:Math.floor(t/3600),minutes:Math.floor(t%3600/60),seconds:t%60}}(t):"time"===e.kind?Wi(e,t):t}(i,o):o,{domain:Me,service:"set_profile",data:s}}const an=["all","sun","hold","off"],ln=["auto","hold","off"],cn=[{key:"1h",ms:()=>36e5},{key:"2h",ms:()=>72e5},{key:"4h",ms:()=>144e5},{key:"tonight",ms:function(e){const t=new Date(e);return t.setHours(24,0,0,0),t.getTime()-e}}],dn=864e5,hn=`/config/integrations/integration/${Me}`;function un(e){return"auto"===e.s.mode&&e.s.sunOnGlass}function pn(e,t){return`${e.id??""}|${t.id??""}`}let gn=class extends ce{constructor(){super(...arguments),this._filter="all",this._selected=null,this._width=0,this._expanded={},this._registry=null,this._settings=null,this._menu=null,this._stored=null,this._overlay={},this._saving=!1,this._watched=[],this._registryFor=null,this._resizeObserver=null,this._cancelMinuteTimer=null,this._focusSheet=!1,this._storedToken=0,this._house=null,this._onKeydown=e=>{"Escape"===e.key&&(this._menu?this._menu=null:(this._selected=null,this._closeSettings()))}}setConfig(e){if(!e||"object"!=typeof e)throw new Error("Invalid configuration");for(const t of["floors","areas"]){const o=e[t];if(!(void 0===o||Array.isArray(o)&&o.every(e=>"string"==typeof e)))throw new Error(`adaptive-cover-house-card: \`${t}\` must be a list of ids`)}this._config={...e}}static getStubConfig(){return{type:`custom:${Ae}`}}static getConfigForm(){return{schema:[{name:"title",selector:{text:{}}},{name:"floors",selector:{floor:{multiple:!0}}},{name:"areas",selector:{area:{multiple:!0}}},{name:"layout",selector:{select:{mode:"dropdown",options:["auto","wide","narrow"].map(e=>({value:e,label:Ve(`editor.house.layout_${e}`)}))}}},{name:"show_upcoming",selector:{boolean:{}}}],computeLabel:e=>Ve(`editor.house.${e.name}`),computeHelper:e=>{const t=`editor.house.${e.name}_help`,o=Ve(t);return o===t?void 0:o}}}getCardSize(){return 12}getGridOptions(){return{columns:"full",rows:"auto",min_columns:6}}connectedCallback(){super.connectedCallback(),this._cancelMinuteTimer??(this._cancelMinuteTimer=Po(()=>this.requestUpdate())),"undefined"==typeof ResizeObserver||this._resizeObserver||(this._resizeObserver=new ResizeObserver(e=>{const t=e[0]?.contentRect.width??0;Math.abs(t-this._width)>=1&&(this._width=t)}),this._resizeObserver.observe(this))}disconnectedCallback(){super.disconnectedCallback(),this._cancelMinuteTimer?.(),this._cancelMinuteTimer=null,this._resizeObserver?.disconnect(),this._resizeObserver=null,window.removeEventListener("keydown",this._onKeydown)}shouldUpdate(e){if(!this._config)return!1;if(1!==e.size||!e.has("hass"))return!0;const t=e.get("hass");if(!t||!this.hass)return!0;const o=t,i=this.hass;return o.entities!==i.entities||o.devices!==i.devices||o.areas!==i.areas||o.floors!==i.floors||o.locale!==i.locale||fe(t,this.hass,this._watched)}updated(e){if((e.has("_selected")||e.has("_settings")||e.has("_menu"))&&(this._selected||this._settings||this._menu?window.addEventListener("keydown",this._onKeydown):window.removeEventListener("keydown",this._onKeydown),(e.has("_selected")&&this._selected||e.has("_settings")&&this._settings)&&(this._focusSheet=!0)),this._focusSheet){const e=this.renderRoot.querySelector(".sheet .close");e&&(this._focusSheet=!1,e.focus())}}_model(){const e=this._config,t=gs(this.hass,this._registry,{floors:e.floors,areas:e.areas}),o=this.hass.entities;return t.needsRegistry&&this._registryFor!==o&&(this._registryFor=o,Yt(this.hass,null!==this._registry).then(e=>{this._registry=Array.isArray(e)?e:[]}).catch(()=>{})),t}_filtered(){const e=this._config;return(e.floors?.length??0)>0||(e.areas?.length??0)>0}_scope(e){return{hub:e.hub,windows:e.windows,useHub:!this._filtered()}}_narrow(){const e=this._config?.layout??"auto";return"narrow"===e||"wide"!==e&&this._width>0&&this._width<600}_views(e){return e.floors.map(e=>{const t=e.rooms.map(t=>{const o=t.windows.map(o=>({w:o,s:Es(this.hass,o),floor:e,room:t}));return{room:t,key:pn(e,t),all:o,shown:o.filter(e=>function(e,t){switch(t){case"sun":return un(e);case"hold":return"hold"===e.s.mode;case"off":return"off"===e.s.mode;default:return!0}}(e,this._filter)),mode:As(o.map(e=>e.s.mode)),sunCount:o.filter(un).length}});return{floor:e,rooms:t,total:t.reduce((e,t)=>e+t.all.length,0)}})}async _run(e){if(0===e.length)return!0;try{return await async function(e,t){for(const o of t)await e.callService(o.domain,o.service,o.data)}(this.hass,e),!0}catch(e){const t=e instanceof Error?e.message:String(e);return this.dispatchEvent(new CustomEvent("hass-notification",{detail:{message:Ve("house.action_failed",{message:t})},bubbles:!0,composed:!0})),!1}}_setWindows(e,t){this._run(Rs(this.hass,e,t))}_navigate(e,t){e.preventDefault(),history.pushState(null,"",t),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}})),this._selected=null,this._closeSettings()}_openSettings(e){this._menu=null,this._selected=null,this._overlay={},this._stored=null,this._settings=e,this._loadStored()}_closeSettings(){this._settings=null,this._overlay={},this._storedToken+=1}async _loadStored(){const e=this._house;if(!e)return;const t=++this._storedToken,o=e.hub.modeSelect??e.hub.cover??Object.values(e.hubSettings).find(e=>!!e),i=await async function(e,t){if(!t)return null;const o=e.user;if(o&&!1===o.is_admin)return null;try{const o=await async function(e,t){const o=Lt()?.find(e=>e.entity_id===t)?.config_entry_id;if(o)return o;const i=await e.callWS({type:"config/entity_registry/get",entity_id:t});return i?.config_entry_id??null}(e,t);if(!o)return null;const i=await e.callApi("GET",`diagnostics/config_entry/${encodeURIComponent(o)}`);return function(e){if(!e||"object"!=typeof e)return null;const t=e,o=e=>e&&"object"==typeof e&&!Array.isArray(e)?e:{};if(!t.house||"object"!=typeof t.house)return null;const i=e=>Object.fromEntries(Object.entries(o(e)).map(([e,t])=>[e,o(t)]));return{house:o(t.house),floors:i(t.floors),areas:i(t.areas)}}(i?.data?.config_options)}catch{return null}}(this.hass,o);t===this._storedToken&&(this._stored=i)}async _saveSetting(e,t){const o=this._settings,i=this._house;if(!o||!i||this._saving)return;const s="house"===o.level?function(e,t,o){const i=e.hubSettings?.[t],s=Ni.get(t);return i&&s&&null!==o?"bool"===s.kind?[{domain:"switch",service:o?"turn_on":"turn_off",data:{entity_id:[i]}}]:[{domain:"number",service:"set_value",data:{entity_id:[i],value:o}}]:[rn({level:"house",id:null},t,o)]}(i,e,t):[rn(o,e,t)];this._saving=!0;const n=await this._run(s);this._saving=!1,n&&this._settings===o&&(this._overlay={...this._overlay,[e]:t},this._loadStored())}_houseSheetAvailable(e){return!this._filtered()&&Pi.some(t=>!!e.hubSettings[t])}_areaScope(e){return e.id?{level:"area",id:e.id,name:e.name}:null}_floorScope(e){return e.id?{level:"floor",id:e.id,name:e.name}:null}render(){if(!this._config||!this.hass)return Y;const e=this._model();this._house=e,this._watched=function(e){const t=new Set;for(const o of e.windows){for(const e of Object.values(o.entities))e&&t.add(e);for(const e of o.covers)t.add(e)}for(const o of Object.values(e.hub))o&&t.add(o);for(const o of Object.values(e.hubSettings??{}))o&&t.add(o);return t.add("sun.sun"),[...t]}(e);const t=Date.now(),o=this._views(e),i=o.flatMap(e=>e.rooms.flatMap(e=>e.all)),s=this._narrow();if(0===i.length)return G`<ha-card>
        <div class="root ${s?"narrow":"wide"}">
          ${this._renderHeader(e,o,s)}
          <p class="empty">${Ve("house.empty")}</p>
        </div>
      </ha-card>`;const n=this._selected?i.find(e=>e.w.key===this._selected):void 0;return G`<ha-card
      @click=${()=>{this._menu&&(this._menu=null)}}
    >
      <div class="root ${s?"narrow":"wide"}">
        ${this._renderHeader(e,o,s)} ${this._renderHouseBar(e,i,s)}
        ${s?o.map(e=>this._renderPhoneFloor(e,t)):G`${this._renderFilters(i)} ${this._renderWide(o,i,t)}`}
      </div>
      ${n?this._renderSheet(n,t,s):Y}
      ${this._settings?this._renderSettingsSheet(e,this._settings,s):Y}
    </ha-card>`}_renderHeader(e,t,o){const i=function(e,t=!1){const o=e.states["sun.sun"];if(!o)return null;const i=o.attributes;if("above_horizon"===o.state&&"number"==typeof i.elevation){const o=Gs(e,i.next_setting);return Ve(t?"house.sun_up_short":"house.sun_up",{azimuth:Math.round(i.azimuth??0),elevation:Math.round(i.elevation),time:o})}const s=Gs(e,i.next_rising);return s?Ve("house.sun_down",{time:s}):Ve("house.sun_down_plain")}(this.hass,o),s=t.reduce((e,t)=>e+t.rooms.length,0),n=t.filter(e=>null!==e.floor.id).length,r=[Hs("window",e.windows.length),Hs("room",s)];return n>0&&r.push(Hs("floor",n)),G`<header class="top">
      <div class="titles">
        <h1>${this._config?.title||Ve("house.title")}</h1>
        ${o?Y:G`<div class="muted sub">${r.join(" · ")}</div>`}
      </div>
      ${i?G`<div class="sun-pill">
            <ha-icon icon="mdi:white-balance-sunny"></ha-icon><span>${i}</span>
          </div>`:Y}
    </header>`}_houseLabel(e,t){const o=As(e);if("mixed"===o){const o=function(e){const t={auto:0,hold:0,off:0};for(const o of e)t[o]+=1;return t}(e);return Ve(t?"house.mixed_short":"house.mixed_long",o)}return Ve(`house.all_${o??"auto"}`)}_renderHouseBar(e,t,o){const i=this._scope(e),s=t.map(e=>e.s.mode),n=As(s),r=i.useHub&&e.hub.modeSelect?!!xs(ws(this.hass,e.hub.modeSelect)):zs(this.hass,e.windows);const a=this._filtered()?Ve("house.these_windows"):Ve("house.whole_house"),l=this._segmented(n,Ve("house.house_mode_label"),r,e=>{this._run(function(e,t,o){const{hub:i,windows:s,useHub:n}=t;if(!n||!i.modeSelect)return Rs(e,s,o);const r=s.map(t=>Ss(e,t));if(r.length>0&&r.every(e=>e===o))return[];const a=ws(e,i.modeSelect);if("off"===o){const t=bs(a);return t?[Is(t,[i.modeSelect])]:Rs(e,s,"off")}if("hold"===o){const t=xs(a);return t?[Is(t,[i.modeSelect])]:Rs(e,s,"hold")}return Ns(e,t)}(this.hass,i,e))},"lg"),c=G`<button
      type="button"
      class="btn return-all"
      @click=${()=>{this._run(Ns(this.hass,i))}}
    >
      ${Ve("house.return_all")}
    </button>`,d=e.hubDeviceId?`/config/devices/device/${encodeURIComponent(e.hubDeviceId)}`:hn,h=this._houseSheetAvailable(e),u=G`<a
      class="link settings"
      href=${d}
      aria-haspopup=${h?"dialog":Y}
      @click=${e=>{h?(e.preventDefault(),this._openSettings({level:"house",id:null,name:""})):this._navigate(e,d)}}
      ><ha-icon icon="mdi:tune-variant"></ha-icon>${Ve(o?"house.settings_short":"house.settings")}</a
    >`;return o?G`<section class="house-bar narrow-bar">
        <div class="bar-head">
          <span class="bar-title">${a}</span>
          <span class="muted">${this._houseLabel(s,!0)}</span>
        </div>
        ${l}
        <div class="bar-row">${c} ${u}</div>
      </section>`:G`<section class="house-bar">
      <div class="bar-label">
        <div class="eyebrow">${a}</div>
        <div class="bar-state">${this._houseLabel(s,!1)}</div>
      </div>
      ${l} ${c}
      <div class="pair">
        <button
          type="button"
          class="btn open-all"
          @click=${()=>{this._run(Ks(i,"open"))}}
        >
          ${Ve("house.open_all")}
        </button>
        <button
          type="button"
          class="btn close-all"
          @click=${()=>{this._run(Ks(i,"close"))}}
        >
          ${Ve("house.close_all")}
        </button>
      </div>
      <div class="grow"></div>
      ${this._renderClimate(e.windows,i)} ${u}
    </section>`}_renderClimate(e,t){const o=function(e,t,o){const i=Bs(e,o);if(i)return"on"===ys(e,i)?"on":"off";const s=t.map(t=>ys(e,t.entities.climateSwitch)).filter(e=>"on"===e||"off"===e);return 0===s.length?null:s.every(e=>"on"===e)?"on":s.every(e=>"off"===e)?"off":"mixed"}(this.hass,e,t);if(null===o)return Y;let i;if("on"===o){const t=function(e,t){const o=new Map;for(const i of t){if("on"!==ys(e,i.entities.climateSwitch))continue;const t=ys(e,i.entities.controlMethod);"winter"!==t&&"summer"!==t&&"intermediate"!==t||o.set(t,(o.get(t)??0)+1)}let i=null,s=0;for(const[e,t]of o)t>s&&(i=e,s=t);return i}(this.hass,e);i=Ve(`house.climate_state.${t??"on"}`)}else if("off"===o)i=Ve("house.climate_state.off");else{const t=e.filter(e=>e.entities.climateSwitch),o=t.filter(e=>"on"===this.hass.states[e.entities.climateSwitch]?.state).length;i=Ve("house.climate_state.mixed",{on:o,total:t.length})}return G`<button
      type="button"
      class="btn climate ${o}"
      aria-pressed=${"on"===o?"true":"off"===o?"false":"mixed"}
      @click=${()=>{this._run(function(e,t,o,i){const s=o?Bs(o,i):null;if(s)return[Ts("switch",t?"turn_on":"turn_off",[s])];const n=e.map(e=>e.entities.climateSwitch).filter(e=>!!e);return n.length>0?[Ts("switch",t?"turn_on":"turn_off",n)]:[]}(e,"on"!==o,this.hass,t))}}
    >
      <span class="track"><span class="knob"></span></span>
      <span class="strong">${Ve("house.climate")}</span>
      <span class="muted">${i}</span>
    </button>`}_segmented(e,t,o,i,s){return G`<div class="seg ${s}" role="group" aria-label=${t}>
      ${ln.map(t=>{const s=e===t,n="hold"===t&&!o;return G`<button
          type="button"
          class="seg-btn ${t} ${s?"on":""}"
          data-mode=${t}
          aria-pressed=${s?"true":"false"}
          aria-disabled=${n?"true":"false"}
          title=${n?Ve("house.hold_disabled"):Y}
          @click=${()=>{n||s||i(t)}}
        >
          ${Ve(`house.mode.${t}`)}
        </button>`})}
    </div>`}_renderFilters(e){const t={all:e.length,sun:e.filter(un).length,hold:e.filter(e=>"hold"===e.s.mode).length,off:e.filter(e=>"off"===e.s.mode).length};return G`<div class="filters" role="group" aria-label=${Ve("house.filter.label")}>
      ${an.map(e=>G`<button
            type="button"
            class="chip-btn ${this._filter===e?"on":""}"
            data-filter=${e}
            aria-pressed=${this._filter===e?"true":"false"}
            @click=${()=>this._filter=e}
          >
            ${Ve(`house.filter.${e}`,{n:t[e]})}
          </button>`)}
    </div>`}_renderWide(e,t,o){const i=e.map(e=>({...e,rooms:e.rooms.filter(e=>e.shown.length>0)})).filter(e=>e.rooms.length>0),s=!1===this._config?.show_upcoming?[]:this._upcoming(t,o),n=[];for(const e of i){const t=n[n.length-1];e.rooms.length>1?n.push({wide:e}):t&&"pack"in t?t.pack.push(e):n.push({pack:[e]})}const r=s.length>0?this._renderUpcoming(s):Y,a=n[n.length-1],l=!!a&&"pack"in a;return G`${0===i.length?G`<p class="empty">${Ve("house.empty_filter")}</p>`:Y}
    ${n.map((e,t)=>"wide"in e?G`<section class="floor">
            ${this._floorHead(e.wide)}
            <div class="grid">${e.wide.rooms.map(e=>this._renderRoom(e,o))}</div>
          </section>`:G`<div class="grid">
            ${e.pack.map(e=>G`<section class="floor">
                  ${this._floorHead(e)} ${e.rooms.map(e=>this._renderRoom(e,o))}
                </section>`)}
            ${l&&t===n.length-1?r:Y}
          </div>`)}
    ${l?Y:r}`}_floorHead(e){return e.floor.name?G`<div class="floor-head" data-floor=${e.floor.id??""}>
      <h2>${e.floor.name}</h2>
      <span class="muted">${Hs("window",e.total)}</span>
      ${this._floorMenu(e.floor)}
    </div>`:Y}_floorMenu(e){const t=this._floorScope(e);return t?this._renderMenu(`floor:${e.id}`,e.name,[{key:"floor-settings",label:Ve("house.floor_settings"),run:()=>this._openSettings(t)}]):Y}_roomMenu(e){const t=this._areaScope(e);return t?this._renderMenu(`area:${e.id}`,e.name,[{key:"room-settings",label:Ve("house.room_settings"),run:()=>this._openSettings(t)}]):Y}_renderMenu(e,t,o){const i=this._menu===e;return G`<span class="menu-wrap">
      <button
        type="button"
        class="menu-btn"
        data-menu=${e}
        aria-haspopup="menu"
        aria-expanded=${i?"true":"false"}
        aria-label=${Ve("house.menu",{name:t})}
        @click=${t=>{t.stopPropagation(),this._menu=i?null:e}}
      >
        <ha-icon icon="mdi:dots-vertical"></ha-icon>
      </button>
      ${i?G`<div class="menu" role="menu">
            ${o.map(e=>G`<button
                  type="button"
                  role="menuitem"
                  class="menu-item"
                  data-item=${e.key}
                  @click=${t=>{t.stopPropagation(),this._menu=null,e.run()}}
                >
                  ${e.label}
                </button>`)}
          </div>`:Y}
    </span>`}_roomSummary(e){const t=[Hs("window",e.all.length)];return e.sunCount>0&&t.push(Ve("house.room_sun",{n:e.sunCount})),"mixed"===e.mode&&t.push(Ve("house.room_mixed")),t.join(" · ")}_roomSegments(e,t){const o=e.all.map(e=>e.w);return this._segmented(e.mode,Ve("house.room_mode_label",{room:e.room.name}),zs(this.hass,o),e=>this._setWindows(o,e),t)}_renderRoom(e,t){return G`<div class="room" data-room=${e.room.id??""}>
      <div class="room-head">
        <div class="room-title">
          <h3>${e.room.name}</h3>
          <span class="muted">${this._roomSummary(e)}</span>
        </div>
        <div class="room-tools">${this._roomSegments(e,"sm")} ${this._roomMenu(e.room)}</div>
      </div>
      ${e.shown.map(e=>this._renderRow(e,t))}
    </div>`}_glyph(e,t=!1){const o=null===e.position?0:Math.max(0,Math.min(100,100-e.position));return G`<span
      class="glyph ${t?"big":""} ${e.sunOnGlass?"sun":""}"
      style="--fabric: ${o}%"
      aria-hidden="true"
      ><span class="fabric"></span
    ></span>`}_renderRow(e,t){const{w:o,s:i}=e;return G`<button
      type="button"
      class="row"
      data-window=${o.key}
      @click=${()=>this._selected=o.key}
    >
      ${this._glyph(i)}
      <span class="row-main">
        <span class="row-name"
          >${o.name}${un(e)?G`<ha-icon
                class="sun-icon"
                icon="mdi:white-balance-sunny"
                title=${Ve("house.sun_on_glass")}
              ></ha-icon>`:Y}</span
        >
        <span class="row-next muted">${Xs(this.hass,i,t)}</span>
      </span>
      <span class="row-end">
        <span class="pos">${qs(i)}</span>
        <span class="chip ${i.mode}">${Js(i,t)}</span>
      </span>
    </button>`}_renderPhoneFloor(e,t){return 0===e.rooms.length?Y:G`<section class="floor">
      ${e.floor.name?G`<div class="phone-floor-head" data-floor=${e.floor.id??""}>
            <h2 class="phone-floor">${e.floor.name}</h2>
            ${this._floorMenu(e.floor)}
          </div>`:Y}
      ${e.rooms.map(e=>this._renderPhoneRoom(e,t))}
    </section>`}_renderPhoneRoom(e,t){const o=e.all.some(e=>"auto"!==e.s.mode),i=this._expanded[e.key]??o,s=e.mode??"auto";return G`<div class="room phone-room" data-room=${e.room.id??""}>
      <button
        type="button"
        class="room-toggle"
        aria-expanded=${i?"true":"false"}
        @click=${()=>this._expanded={...this._expanded,[e.key]:!i}}
      >
        <span class="room-title">
          <span class="strong">${e.room.name}</span>
          <span class="muted">${this._roomSummary(e)}</span>
        </span>
        <span class="chip ${s}">${Ve(`house.mode.${s}`)}</span>
        <ha-icon class="chevron ${i?"open":""}" icon="mdi:chevron-right"></ha-icon>
      </button>
      ${i?G`<div class="room-body">
            ${this._roomSegments(e,"lg")} ${e.all.map(e=>this._renderRow(e,t))}
            ${e.room.id?G`<button
                  type="button"
                  class="btn room-settings"
                  @click=${()=>{const t=this._areaScope(e.room);t&&this._openSettings(t)}}
                >
                  <ha-icon icon="mdi:tune-variant"></ha-icon>${Ve("house.room_settings")}
                </button>`:Y}
          </div>`:Y}
    </div>`}_upcoming(e,t){const o=[];for(const i of e){if("auto"!==i.s.mode||!i.s.nextMove)continue;const e=Date.parse(i.s.nextMove.time);if(Number.isNaN(e)||e<t-6e4||e>t+dn)continue;const s=Math.floor(e/6e4),n=o.find(e=>Math.floor(e.at/6e4)===s&&e.position===i.s.nextMove.position);n?n.names.push(i.w.deviceName):o.push({at:e,time:i.s.nextMove.time,position:i.s.nextMove.position,names:[i.w.deviceName]})}const i=o.map(e=>({at:e.at,time:Gs(this.hass,e.time),what:e.names.join(", "),detail:null===e.position?Ve("house.upcoming.changes"):Ve("house.upcoming.follows",{position:`${Math.round(e.position)}%`})})),s=this.hass.states["sun.sun"],n="above_horizon"===s?.state?s.attributes?.next_setting:void 0,r="string"==typeof n?Date.parse(n):NaN;return!Number.isNaN(r)&&r>t&&r<t+dn&&i.push({at:r,time:Gs(this.hass,n),what:Ve("house.upcoming.sunset"),detail:Ve("house.upcoming.sunset_detail")}),i.sort((e,t)=>e.at-t.at),i.slice(0,5)}_renderUpcoming(e){return G`<section class="floor upcoming">
      <div class="floor-head">
        <h2>${Ve("house.upcoming.title")}</h2>
        <span class="muted">${Ve("house.upcoming.today")}</span>
      </div>
      <div class="room upcoming-list">
        ${e.map(e=>G`<div class="up-row">
              <span class="up-time">${e.time}</span>
              <span class="up-main">
                <span class="strong">${e.what}</span>
                <span class="muted">${e.detail}</span>
              </span>
            </div>`)}
      </div>
    </section>`}_renderSettingsSheet(e,t,o){const i=function(e,t,o,i,s={}){const n=new nn(e,t,i),r=(a=o.level,"house"===a?Pi.map(e=>Ni.get(e)):Ii.flatMap(e=>ji.filter(t=>t.section===e&&t.levels.includes(a)))).filter(e=>"house"!==o.level||!!t.hubSettings?.[e.key]);var a;return r.map(e=>{const i=e.key,r=n.houseValue(e),a=n.exceptions(o,e);if("house"===o.level){const t=sn(s,i)?s[i]:r;return{setting:e,own:!0,value:t,inherited:null,houseValue:t,exceptions:a}}const l=o.id;let{own:c,value:d}=n.own(o.level,l,e);sn(s,i)&&(c=null!==s[i],d=c?s[i]:void 0);let h={level:"house",name:null,value:r};if("area"===o.level&&e.levels.includes("floor")){const o=function(e,t){for(const o of e.floors)if(null!==o.id&&o.rooms.some(e=>e.id===t))return{id:o.id,name:o.name};return null}(t,l),i=o?n.own("floor",o.id,e):null;!o||!i?.own&&e.levels.includes("house")||(h={level:"floor",name:o.name,value:i?.value})}return{setting:e,own:c,value:d,inherited:h,houseValue:r,exceptions:a}})}(this.hass,e,t,this._stored,this._overlay),s=e.windows.filter(e=>"area"===t.level?e.areaId===t.id:"floor"===t.level&&e.floorId===t.id),n=function(e,t){const o=[];for(const i of t){const t=tn(e,i);if(!t)continue;const s=Object.entries(t).filter(([,e])=>"window"===e||"legacy"===e).map(([e,t])=>({key:e,legacy:"legacy"===t})).sort((e,t)=>e.key.localeCompare(t.key));s.length>0&&o.push({window:i,settings:s})}return o}(this.hass,s),r=Ve(`settings.title.${t.level}`,{name:t.name}),a=e.hubDeviceId?`/config/devices/device/${encodeURIComponent(e.hubDeviceId)}`:hn;return G`<div class="scrim" @click=${()=>this._closeSettings()}></div>
      <aside
        class="sheet settings-sheet ${o?"bottom":"side"}"
        role="dialog"
        aria-modal="true"
        aria-label=${Ve("settings.sheet_label",{name:r})}
        data-level=${t.level}
        data-id=${t.id??""}
      >
        <div class="sheet-head">
          <div class="sheet-title">
            <span class="muted">${Ve(`settings.eyebrow.${t.level}`)}</span>
            <h2>${r}</h2>
          </div>
          <button
            type="button"
            class="close icon-btn"
            aria-label=${Ve("settings.close")}
            @click=${()=>this._closeSettings()}
          >
            <ha-icon icon="mdi:close"></ha-icon>
          </button>
        </div>
        <p class="muted intro">${Ve(`settings.intro.${t.level}`)}</p>
        <acp-settings-sheet
          .hass=${this.hass}
          .scope=${t}
          .rows=${i}
          .windows=${n}
          ?busy=${this._saving}
          @acp-setting-set=${e=>{this._saveSetting(e.detail.key,e.detail.value)}}
          @acp-setting-reset=${e=>{this._saveSetting(e.detail.key,null)}}
          @acp-open-window=${e=>{this._closeSettings(),this._selected=e.detail.key}}
        ></acp-settings-sheet>
        ${"house"===t.level?G`<div class="sheet-foot">
              <span class="setup">
                <a
                  class="link more"
                  href=${a}
                  @click=${e=>this._navigate(e,a)}
                  >${Ve("settings.more")}</a
                >
                <span class="muted">${Ve("settings.more_hint")}</span>
              </span>
            </div>`:Y}
      </aside>`}_renderSheet(e,t,o){const{w:i,s:s}=e,n=[e.floor.name,e.room.name].filter(Boolean).join(" · "),r=zs(this.hass,[i]),a=ni(si({window_key:i.key,config_entry_id:i.configEntryId,config_subentry_id:i.configSubentryId})),l=function(e){return null===e.azimuth?null:Ve("house.sheet.faces",{deg:Math.round(e.azimuth),dir:Ys(e.azimuth)})}(s),c=e=>()=>{this._run(Ds([i],e))},d=null!==s.target&&null!==s.position&&Math.round(s.target)!==Math.round(s.position);return G`<div class="scrim" @click=${()=>this._selected=null}></div>
      <aside
        class="sheet ${o?"bottom":"side"}"
        role="dialog"
        aria-modal="true"
        aria-label=${Ve("house.sheet.label")}
      >
        <div class="sheet-head">
          <div class="sheet-title">
            <span class="muted">${n}</span>
            <h2>${i.name}</h2>
          </div>
          <button
            type="button"
            class="close icon-btn"
            aria-label=${Ve("house.sheet.close")}
            @click=${()=>this._selected=null}
          >
            <ha-icon icon="mdi:close"></ha-icon>
          </button>
        </div>
        <div class="sheet-pos">
          ${this._glyph(s,!0)}
          <div class="sheet-pos-text">
            <span class="big-pos">${qs(s)}</span>
            <span class="muted">${Ve("house.sheet.open_word")}</span>
            ${d?G`<span class="muted target"
                  >${Ve("house.sheet.target",{position:`${Math.round(s.target)}%`})}</span
                >`:Y}
            <span class="chip ${s.mode}">${Js(s,t)}</span>
          </div>
        </div>
        <div class="cmds">
          <button type="button" class="btn cmd-open" @click=${c("open")}>
            ${Ve("house.sheet.open")}
          </button>
          <button type="button" class="btn cmd-stop" @click=${c("stop")}>
            ${Ve("house.sheet.stop")}
          </button>
          <button type="button" class="btn cmd-close" @click=${c("close")}>
            ${Ve("house.sheet.close_cover")}
          </button>
        </div>
        <div class="mode-block">
          <span class="eyebrow">${Ve("house.sheet.mode")}</span>
          ${this._segmented(s.mode,Ve("house.window_mode_label"),r,e=>this._setWindows([i],e),"lg")}
          ${r?G`<div class="hold-chips" role="group" aria-label=${Ve("house.sheet.hold_for")}>
                <span class="muted">${Ve("house.sheet.hold_for")}</span>
                ${cn.map(e=>G`<button
                      type="button"
                      class="btn hold-chip"
                      data-hold=${e.key}
                      @click=${()=>{this._run(js(this.hass,[i],e.ms(Date.now())))}}
                    >
                      ${Ve(`house.sheet.hold_${e.key}`)}
                    </button>`)}
              </div>`:G`<p class="hint muted">${Ve("house.sheet.hold_hint")}</p>`}
        </div>
        <div class="why">
          <span class="eyebrow">${Ve("house.why.title")}</span>
          <p class="why-text">${function(e,t){if("off"===t.mode)return Ve("house.why.off");if("hold"===t.mode){const o=Gs(e,t.holdUntil);return o?Ve("house.why.hold",{time:o}):Ve("house.why.hold_unknown")}const o=(i=t.intent)?ze.includes(i)?Ve(`handler.${i}`):i:null;var i;const s=t.trace.length>0?t.trace[t.trace.length-1]:"";return o&&s?`${o}: ${s}`:o||s||Ve("house.why.none")}(this.hass,s)}</p>
          <p class="muted">${Xs(this.hass,s,t)}</p>
          ${"auto"===s.mode&&s.trace.length>1?G`<details>
                <summary>${Ve("house.why.steps")}</summary>
                <ol>
                  ${s.trace.map(e=>G`<li>${e}</li>`)}
                </ol>
              </details>`:Y}
        </div>
        <div class="grow"></div>
        <div class="sheet-foot">
          <span class="setup">
            <a class="link" href=${a} @click=${e=>this._navigate(e,a)}
              >${Ve("house.sheet.setup")}</a
            >
            <span class="muted">${Ve("house.sheet.setup_hint")}</span>
          </span>
          ${l?G`<span class="muted">${l}</span>`:Y}
        </div>
      </aside>`}};gn.styles=r`
    :host {
      display: block;
      --acp-auto: var(--primary-color, #03a9f4);
      --acp-on-auto: var(--text-primary-color, #fff);
      --acp-hold: var(--warning-color, #ffa600);
      --acp-on-hold: #1f1f1f;
      --acp-off: var(--secondary-text-color, #727272);
      --acp-on-off: var(--card-background-color, #fff);
      --acp-sun: var(--amber-color, #ffc107);
      --acp-sun-strong: var(--orange-color, #ff9800);
      --acp-line: var(--divider-color, rgba(0, 0, 0, 0.12));
      --acp-surface: var(--card-background-color, var(--ha-card-background, #fff));
      --acp-track: var(--secondary-background-color, #efefef);
      --acp-radius: 14px;
    }
    .root {
      display: flex;
      flex-direction: column;
      gap: 20px;
      padding: 20px 24px 24px;
      color: var(--primary-text-color);
      font-variant-numeric: tabular-nums;
    }
    .root.narrow {
      gap: 14px;
      padding: 16px;
    }
    .muted {
      color: var(--secondary-text-color);
    }
    .strong {
      font-weight: 600;
    }
    .eyebrow {
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.6px;
    }
    .grow {
      flex-grow: 1;
    }
    .empty {
      margin: 0;
      color: var(--secondary-text-color);
    }
    button {
      font: inherit;
      cursor: pointer;
    }
    button:focus-visible,
    a:focus-visible {
      outline: 3px solid var(--acp-auto);
      outline-offset: 2px;
    }
    .link {
      color: var(--primary-color);
      font-weight: 600;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .link ha-icon {
      --mdc-icon-size: 18px;
    }

    /* Header */
    .top {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      gap: 12px;
      flex-wrap: wrap;
    }
    .narrow .top {
      align-items: center;
    }
    .titles {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    h1 {
      margin: 0;
      font-size: 2.2rem;
      font-weight: 600;
      letter-spacing: -0.5px;
      line-height: 1.1;
    }
    .narrow h1 {
      font-size: 1.8rem;
    }
    .sub {
      font-size: 0.95rem;
    }
    .sun-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 14px;
      border-radius: 999px;
      font-weight: 600;
      font-size: 0.95rem;
      background: rgba(255, 193, 7, 0.16);
      background: color-mix(in srgb, var(--acp-sun) 18%, transparent);
    }
    .sun-pill ha-icon {
      --mdc-icon-size: 18px;
      color: var(--acp-sun-strong);
    }
    .narrow .sun-pill {
      padding: 6px 12px;
      font-size: 0.85rem;
    }

    /* Buttons */
    .btn {
      min-height: 44px;
      padding: 0 16px;
      border: 1px solid var(--acp-line);
      border-radius: 10px;
      background: var(--acp-surface);
      color: var(--primary-text-color);
      font-weight: 600;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
    }
    .btn:hover {
      background: var(--acp-track);
    }
    .pair {
      display: flex;
      gap: 8px;
    }

    /* Whole-house bar */
    .house-bar {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px 14px;
      padding: 16px 20px;
      border: 1px solid var(--acp-line);
      border-radius: 16px;
    }
    .bar-label {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 170px;
    }
    .house-bar:not(.narrow-bar) .settings {
      margin-left: auto;
    }
    .bar-state {
      font-size: 1.05rem;
      font-weight: 600;
    }
    .narrow-bar {
      flex-direction: column;
      align-items: stretch;
      gap: 12px;
      padding: 14px;
    }
    .bar-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 8px;
    }
    .bar-title {
      font-size: 1.05rem;
      font-weight: 700;
    }
    .bar-row {
      display: flex;
      gap: 8px;
    }
    .bar-row .return-all {
      flex-grow: 1;
    }
    .bar-row .settings {
      min-height: 44px;
      padding: 0 12px;
      border: 1px solid var(--acp-line);
      border-radius: 10px;
    }
    .climate {
      padding-left: 8px;
    }
    .climate .track {
      width: 40px;
      height: 24px;
      border-radius: 999px;
      padding: 0 3px;
      box-sizing: border-box;
      display: flex;
      align-items: center;
      background: var(--disabled-text-color, #bdbdbd);
    }
    .climate.on .track {
      justify-content: flex-end;
      background: var(--acp-auto);
    }
    .climate.mixed .track {
      justify-content: center;
      background: var(--acp-hold);
    }
    .climate .knob {
      width: 18px;
      height: 18px;
      border-radius: 999px;
      background: #fff;
    }
    .climate .muted {
      font-weight: 400;
    }

    /* Segmented Auto / Hold / Off */
    .seg {
      display: flex;
      gap: 4px;
      padding: 4px;
      border-radius: 12px;
      background: var(--acp-track);
    }
    .seg.sm {
      gap: 3px;
      padding: 3px;
      border-radius: 10px;
    }
    .seg-btn {
      flex-grow: 1;
      min-height: 44px;
      padding: 0 18px;
      border: none;
      border-radius: 9px;
      background: transparent;
      color: var(--primary-text-color);
      font-weight: 600;
    }
    .seg.sm .seg-btn {
      min-height: 36px;
      padding: 0 10px;
      border-radius: 8px;
      font-size: 0.85rem;
    }
    .seg-btn[aria-disabled='true'] {
      cursor: not-allowed;
      color: var(--disabled-text-color, #9e9e9e);
      opacity: 0.6;
    }
    .seg-btn.on[aria-disabled='true'] {
      opacity: 1;
    }
    .seg-btn.on.auto {
      background: var(--acp-auto);
      color: var(--acp-on-auto);
    }
    .seg-btn.on.hold {
      background: var(--acp-hold);
      color: var(--acp-on-hold);
    }
    .seg-btn.on.off {
      background: var(--acp-off);
      color: var(--acp-on-off);
    }

    /* Filter chips */
    .filters {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .chip-btn {
      min-height: 40px;
      padding: 0 16px;
      border-radius: 999px;
      border: 1px solid var(--acp-line);
      background: var(--acp-surface);
      color: var(--primary-text-color);
      font-weight: 600;
      font-size: 0.9rem;
    }
    .chip-btn.on {
      background: var(--primary-text-color);
      color: var(--acp-surface);
      border-color: var(--primary-text-color);
    }

    /* Floors and rooms */
    .floor {
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-width: 0;
    }
    .floor-head {
      display: flex;
      align-items: baseline;
      gap: 12px;
    }
    h2 {
      margin: 0;
      font-size: 1.25rem;
      font-weight: 700;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
      gap: 16px;
      align-items: start;
    }
    .room {
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: 14px;
      border: 1px solid var(--acp-line);
      border-radius: var(--acp-radius);
      background: var(--acp-surface);
      min-width: 0;
    }
    .room-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 2px 4px 8px;
      flex-wrap: wrap;
    }
    .room-title {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }
    h3 {
      margin: 0;
      font-size: 1.05rem;
      font-weight: 700;
    }
    .room-title .muted {
      font-size: 0.85rem;
    }
    .room-tools {
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .floor-head .menu-wrap {
      margin-left: auto;
    }
    .phone-floor-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .room-settings {
      margin-top: 8px;
      align-self: flex-start;
    }
    .room-settings ha-icon {
      --mdc-icon-size: 18px;
    }

    /* Room and floor menus */
    .menu-wrap {
      position: relative;
      display: inline-flex;
    }
    .menu-btn {
      width: 36px;
      height: 36px;
      border: none;
      border-radius: 10px;
      background: transparent;
      color: var(--secondary-text-color);
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
    .menu-btn:hover,
    .menu-btn[aria-expanded='true'] {
      background: var(--acp-track);
    }
    .menu {
      position: absolute;
      top: calc(100% + 4px);
      right: 0;
      z-index: 5;
      min-width: 180px;
      padding: 4px;
      display: flex;
      flex-direction: column;
      border: 1px solid var(--acp-line);
      border-radius: 12px;
      background: var(--acp-surface);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
    }
    .menu-item {
      min-height: 44px;
      padding: 0 12px;
      border: none;
      border-radius: 8px;
      background: transparent;
      color: var(--primary-text-color);
      font-weight: 600;
      text-align: left;
    }
    .menu-item:hover {
      background: var(--acp-track);
    }

    /* Window rows */
    .row {
      display: flex;
      align-items: center;
      gap: 12px;
      width: 100%;
      min-height: 60px;
      padding: 8px;
      border: none;
      border-radius: 10px;
      background: transparent;
      color: var(--primary-text-color);
      text-align: left;
    }
    .row:hover {
      background: var(--acp-track);
    }
    .row-main {
      display: flex;
      flex-direction: column;
      flex-grow: 1;
      gap: 2px;
      min-width: 0;
    }
    .row-name {
      display: flex;
      align-items: center;
      gap: 6px;
      font-weight: 600;
    }
    .sun-icon {
      --mdc-icon-size: 16px;
      color: var(--acp-sun-strong);
    }
    .row-next {
      font-size: 0.85rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .row-end {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 4px;
    }
    .pos {
      font-size: 1.05rem;
      font-weight: 700;
    }
    .chip {
      font-size: 0.75rem;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 999px;
      white-space: nowrap;
    }
    .chip.auto {
      color: var(--acp-auto);
      background: rgba(3, 169, 244, 0.14);
      background: color-mix(in srgb, var(--acp-auto) 15%, transparent);
    }
    .chip.hold {
      color: var(--primary-text-color);
      background: rgba(255, 166, 0, 0.3);
      background: color-mix(in srgb, var(--acp-hold) 32%, transparent);
    }
    .chip.off,
    .chip.mixed {
      color: var(--primary-text-color);
      background: var(--acp-track);
    }

    /* Shade glyph: the fabric covers (100 - position)% from the top. */
    .glyph {
      width: 28px;
      height: 38px;
      flex-shrink: 0;
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border: 2px solid var(--primary-text-color);
      border-radius: 3px;
      background: rgba(3, 155, 229, 0.16);
      background: color-mix(in srgb, var(--info-color, #039be5) 18%, var(--acp-surface));
    }
    .glyph.sun {
      background: rgba(255, 193, 7, 0.4);
      background: color-mix(in srgb, var(--acp-sun) 45%, var(--acp-surface));
    }
    .glyph .fabric {
      width: 100%;
      height: var(--fabric, 0%);
      box-sizing: border-box;
      background: var(--secondary-text-color);
      opacity: 0.55;
      border-bottom: 2px solid var(--primary-text-color);
    }
    .glyph.big {
      width: 96px;
      height: 128px;
      border-width: 3px;
      border-radius: 5px;
    }

    /* Coming up */
    .upcoming-list {
      padding: 6px 16px;
      gap: 0;
    }
    .up-row {
      display: flex;
      gap: 14px;
      align-items: baseline;
      padding: 10px 0;
      border-bottom: 1px solid var(--acp-line);
    }
    .up-row:last-child {
      border-bottom: none;
    }
    .up-time {
      width: 72px;
      flex-shrink: 0;
      font-weight: 700;
      font-size: 0.9rem;
    }
    .up-main {
      display: flex;
      flex-direction: column;
      gap: 2px;
      font-size: 0.9rem;
    }

    /* Phone */
    .phone-floor {
      margin: 4px 4px 0;
      font-size: 0.95rem;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: var(--secondary-text-color);
    }
    .phone-room {
      padding: 0;
      gap: 0;
      overflow: hidden;
    }
    .room-toggle {
      display: flex;
      align-items: center;
      gap: 10px;
      width: 100%;
      min-height: 60px;
      padding: 10px 14px;
      border: none;
      background: transparent;
      color: var(--primary-text-color);
      text-align: left;
    }
    .room-toggle .room-title {
      flex-grow: 1;
    }
    .chevron {
      --mdc-icon-size: 20px;
      color: var(--secondary-text-color);
      transition: transform 0.15s;
    }
    .chevron.open {
      transform: rotate(90deg);
    }
    .room-body {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 0 14px 12px;
    }
    .room-body .seg {
      margin-bottom: 6px;
    }
    .room-body .row {
      border-top: 1px solid var(--acp-line);
      border-radius: 0;
      padding: 8px 0;
    }

    /* Detail sheet */
    .scrim {
      position: fixed;
      inset: 0;
      z-index: 9998;
      background: rgba(0, 0, 0, 0.32);
    }
    .sheet {
      position: fixed;
      z-index: 9999;
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
      gap: 20px;
      padding: 28px;
      overflow-y: auto;
      background: var(--acp-surface);
      color: var(--primary-text-color);
      box-shadow: -12px 0 40px rgba(0, 0, 0, 0.25);
    }
    .sheet.side {
      top: 0;
      right: 0;
      bottom: 0;
      width: min(440px, 100vw);
    }
    .sheet.bottom {
      left: 0;
      right: 0;
      bottom: 0;
      max-height: 92vh;
      padding: 20px 16px 24px;
      border-radius: 16px 16px 0 0;
      box-shadow: 0 -12px 40px rgba(0, 0, 0, 0.25);
    }
    .sheet-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
    }
    .sheet-title {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .sheet-title h2 {
      font-size: 1.8rem;
      font-weight: 600;
    }
    .icon-btn {
      width: 44px;
      height: 44px;
      flex-shrink: 0;
      border: none;
      border-radius: 10px;
      background: var(--acp-track);
      color: var(--primary-text-color);
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .sheet-pos {
      display: flex;
      gap: 24px;
      align-items: center;
    }
    .sheet-pos-text {
      display: flex;
      flex-direction: column;
      gap: 6px;
      align-items: flex-start;
    }
    .big-pos {
      font-size: 2.8rem;
      font-weight: 700;
      line-height: 1;
    }
    .cmds {
      display: flex;
      gap: 8px;
    }
    .cmds .btn {
      flex-grow: 1;
      min-height: 48px;
    }
    .mode-block {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .hint {
      margin: 0;
      font-size: 0.85rem;
    }
    .hold-chips {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
    }
    .hold-chips .btn {
      min-height: 36px;
      padding: 0 12px;
      border-radius: 18px;
    }
    .why {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 16px;
      border-radius: 12px;
      background: var(--acp-track);
    }
    .why p {
      margin: 0;
      line-height: 1.5;
    }
    .why details {
      font-size: 0.85rem;
      color: var(--secondary-text-color);
    }
    .why ol {
      margin: 6px 0 0;
      padding-left: 20px;
    }
    .sheet-foot {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding-top: 16px;
      border-top: 1px solid var(--acp-line);
    }
    .setup {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .setup .muted,
    .sheet-foot > .muted {
      font-size: 0.85rem;
    }
    .settings-sheet.side {
      width: min(520px, 100vw);
    }
    .settings-sheet .intro {
      margin: -8px 0 0;
      line-height: 1.45;
    }
  `,e([ge({attribute:!1})],gn.prototype,"hass",void 0),e([me()],gn.prototype,"_config",void 0),e([me()],gn.prototype,"_filter",void 0),e([me()],gn.prototype,"_selected",void 0),e([me()],gn.prototype,"_width",void 0),e([me()],gn.prototype,"_expanded",void 0),e([me()],gn.prototype,"_registry",void 0),e([me()],gn.prototype,"_settings",void 0),e([me()],gn.prototype,"_menu",void 0),e([me()],gn.prototype,"_stored",void 0),e([me()],gn.prototype,"_overlay",void 0),e([me()],gn.prototype,"_saving",void 0),gn=e([he(Ae)],gn),window.customCards=window.customCards||[],window.customCards.some(e=>e.type===Ae)||window.customCards.push({type:Ae,name:Ve("house.card_name"),description:Ve("house.card_description"),preview:!1,documentationURL:"https://github.com/mrvollger/adaptive-cover"});class mn extends HTMLElement{static async generate(e,t){return function(e,t){const o=e?.title||Ve("house.title"),i={type:`custom:${Ae}`};e?.title&&(i.title=e.title),e?.floors?.length&&(i.floors=[...e.floors]),e?.areas?.length&&(i.areas=[...e.areas]);const s=gs(t,null,{floors:i.floors,areas:i.areas});return{title:o,views:[{title:o,path:"shades",icon:"mdi:blinds-horizontal",type:"panel",cards:0!==s.windows.length||s.needsRegistry?[i]:[{type:"markdown",content:Ve("house.empty")}]}]}}(e,t)}}customElements.get(Ee)||customElements.define(Ee,mn),window.customStrategies=window.customStrategies||[],window.customStrategies.some(e=>e.type===Ce)||window.customStrategies.push({type:Ce,strategyType:"dashboard",name:Ve("house.strategy_name"),description:Ve("house.strategy_description"),documentationURL:"https://github.com/mrvollger/adaptive-cover"});const fn=["sky","elevation","decision","covers","overrides","climate"];let _n=class extends ce{constructor(){super(...arguments),this._registry=null,this._registryError=null,this._discovered=null,this._discoveredList=[],this._discoveredListSource=null,this._unsubRegistry=null,this._fetchInFlight=!1,this._memo=Bt(),this._debounceTimer=null,this._debounceFirstAt=null,this._DEBOUNCE_DELAY=500,this._DEBOUNCE_MAX=2e3}setConfig(e){const t=yt(e);if(!t)throw new Error("adaptive-cover-card: set `window` (window key) or `cover` (cover entity); a legacy `entry_id` also works.");if(this._config={...e},e.tooltips&&gt(e.tooltips),null===this._registry){const e=Xt.get(bt(t));e&&(this._registry=e.entries)}}get _ref(){return yt(this._config)}_slice(e){const t=this._ref;return t&&this.hass?Kt(this.hass,t,e):[]}getCardSize(){return 6}getGridOptions(){return{columns:12,rows:"auto",min_columns:6,max_columns:12}}static async getConfigElement(){return document.createElement(ye)}static async getStubConfig(e){let t="";try{const o=await Qt(e);t=o[0]?.window_key??""}catch{}return{type:`custom:${ve}`,window:t}}connectedCallback(){if(super.connectedCallback(),null===this._registry){const e=Lt();e&&(this._registry=e)}this.hass&&this._ensureRegistry()}disconnectedCallback(){super.disconnectedCallback(),this._unsubRegistry&&(this._unsubRegistry(),this._unsubRegistry=null),null!==this._debounceTimer&&(clearTimeout(this._debounceTimer),this._debounceTimer=null,this._debounceFirstAt=null)}updated(e){e.has("hass")&&this.hass&&this._ensureRegistry()}shouldUpdate(e){return e.size>1||!e.has("hass")||(!this._discovered||fe(e.get("hass"),this.hass,Object.values(this._discovered.entities)))}willUpdate(e){null!==this._registry&&this._config&&this.hass&&(e.has("hass")||e.has("_registry")||e.has("_config"))&&(this._discovered=this._memo(this.hass,this._config,this._registry)),this._discovered!==this._discoveredListSource&&(this._discoveredListSource=this._discovered,this._discoveredList=this._discovered?[this._discovered]:[])}_ensureRegistry(){this._fetchRegistry(),this._unsubRegistry||(this._unsubRegistry=Vt(this.hass,e=>{const t=new Set(this._slice(this._registry??[]).map(e=>e.entity_id));(function(e,t){return"create"===e.action||t.has(e.entity_id)})(e,t)&&this._scheduleRefetch()}))}_fetchRegistry(e=!1){this._fetchInFlight||(this._fetchInFlight=!0,Yt(this.hass,e).then(e=>{if(e===this._registry)return;const t=this._ref;if(t){const o=this._slice(e);(null===this._registry||function(e,t){if(e.length!==t.length)return!0;const o=new Map(e.map(e=>[e.entity_id,Jt(e)]));for(const e of t)if(o.get(e.entity_id)!==Jt(e))return!0;return!1}(this._slice(this._registry),o))&&(this._registry=e,o.length&&Xt.set(bt(t),o))}else this._registry=e;this._registryError=null}).catch(e=>{this._registryError=e?.message??"entity registry fetch failed"}).finally(()=>{this._fetchInFlight=!1}))}_scheduleRefetch(){const e=Date.now();null===this._debounceFirstAt&&(this._debounceFirstAt=e);const t=e-this._debounceFirstAt,o=this._DEBOUNCE_MAX-t,i=Math.min(this._DEBOUNCE_DELAY,o);if(null!==this._debounceTimer&&clearTimeout(this._debounceTimer),i<=0)return this._debounceFirstAt=null,void this._fetchRegistry(!0);this._debounceTimer=setTimeout(()=>{this._debounceTimer=null,this._debounceFirstAt=null,this._fetchRegistry(!0)},i)}get _sections(){return this._config?.show_sections??fn}_renderHeader(e,t){const o=Te[e.cover_type]??"mdi:window-shutter",i=e.entities.automatic_control_switch,s=!i||"on"===this.hass.states[i]?.state;return G`
      <div class="header">
        <ha-icon .icon=${o}></ha-icon>
        <span class="title">${e.entry_title}</span>
        <span class="spacer"></span>
        ${i?G`<acp-header-pill
              .on=${s}
              .readonly=${!t.automatic_control}
              .label=${Ve("header.auto")}
              title=${Ve("header.automatic_control")}
              @pill-click=${()=>this._toggle(i)}
            ></acp-header-pill>`:Y}
      </div>
    `}_toggle(e){const t=e.split(".")[0];this.hass.callService(t,"toggle",{entity_id:e})}_renderLoading(){return G`
      <ha-card>
        <div class="empty">
          <p class="dim">${Ve("root.loading_registry")}</p>
        </div>
      </ha-card>
    `}_renderEmpty(e){const t=this._ref,o="cover"===t?.kind?"cover":"entry"===t?.kind?"entry_id":"window",i=this._registry?.length??0,s=this._registry?this._slice(this._registry).length:void 0;return G`
      <ha-card>
        <div class="empty">
          <p><strong>${Ve("root.no_entities_title")}</strong></p>
          <p class="dim">
            Configured <code>${o}</code>: <code>${t?xt(t):""}</code>
          </p>
          <ul class="diag">
            <li>Reason: <code>${e}</code></li>
            <li>Registry entries loaded: <code>${i}</code></li>
            <li>Adaptive Cover entities of this window: <code>${s??"—"}</code></li>
            ${this._registryError?G`<li>Registry fetch error: <code>${this._registryError}</code></li>`:Y}
          </ul>
          <p class="dim">
            If the count is 0, the window key is wrong. The Cover Position sensor of each window
            shows its key in the <code>window_key</code> attribute; or pick the window in the card
            editor.
          </p>
        </div>
      </ha-card>
    `}render(){if(!this._config||!this.hass)return Y;if(null===this._registry)return this._registryError?this._renderEmpty("registry fetch failed"):this._renderLoading();const e=this._discovered;if(!e)return this._renderEmpty("no window matches the configured key or cover");const t=(o=this._config,{...Ke,...o?.controls});var o;const i=this._sections;return G`
      <ha-card>
        ${this._renderHeader(e,t)}
        <div class="body ${this._config.compact?"compact":""}">
          ${i.includes("sky")?G`<acp-sky-compass
                .hass=${this.hass}
                .discovered_list=${this._discoveredList}
                ?compact=${!!this._config.compact}
                .showStats=${this._config.show_compass_stats??!0}
                .showLegend=${this._config.show_compass_legend??!0}
                .showMoon=${this._config.show_moon??!1}
                .coverColors=${this._config.cover_colors??[]}
                .northOffsetDeg=${st(this._config.north_offset??0)}
              ></acp-sky-compass>`:Y}
          ${i.includes("elevation")?G`<acp-elevation-chart
                .hass=${this.hass}
                .discoveredList=${this._discoveredList}
                ?compact=${!!this._config.compact}
                .coverColors=${this._config.cover_colors??[]}
              ></acp-elevation-chart>`:Y}
          ${i.includes("decision")?G`<acp-decision-strip
                .hass=${this.hass}
                .discovered=${e}
                ?compact=${!!this._config.compact}
                ?hide-inactive=${!!this._config.hide_inactive_handlers||!!this._config.compact}
                .showSummary=${!1!==this._config.show_decision_summary}
              ></acp-decision-strip>`:Y}
          ${i.includes("covers")?G`<acp-cover-bar
                .hass=${this.hass}
                .discovered=${e}
                ?compact=${!!this._config.compact}
                .coverColor=${this._config.cover_colors?.[0]??null}
              ></acp-cover-bar>`:Y}
          ${i.includes("overrides")?G`<acp-overrides-panel
                .hass=${this.hass}
                .discovered=${e}
                ?compact=${!!this._config.compact}
                .resetEnabled=${t.reset_manual_override}
              ></acp-overrides-panel>`:Y}
          ${i.includes("climate")?G`<acp-climate-panel
                .hass=${this.hass}
                .discovered=${e}
                ?compact=${!!this._config.compact}
              ></acp-climate-panel>`:Y}
        </div>
      </ha-card>
    `}};_n.styles=r`
    :host {
      display: block;
    }
    ha-card {
      padding: 12px 14px 10px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      box-sizing: border-box;
    }
    .header {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      font-weight: 500;
    }
    .header ha-icon {
      --mdc-icon-size: 22px;
      color: var(--primary-color);
    }
    .title {
      font-size: 1.05rem;
    }
    .spacer {
      flex: 1 1 auto;
    }
    .body {
      display: grid;
      gap: 12px;
    }
    .body.compact {
      gap: 8px;
    }
    .empty {
      padding: 16px;
      text-align: center;
    }
    .empty code {
      background: var(--code-editor-background-color, rgba(0, 0, 0, 0.08));
      padding: 1px 6px;
      border-radius: 3px;
    }
    .empty ul.diag {
      list-style: none;
      padding: 0;
      margin: 8px auto;
      text-align: left;
      display: inline-block;
      font-size: 0.82rem;
    }
    .dim {
      color: var(--secondary-text-color);
    }
  `,e([ge({attribute:!1})],_n.prototype,"hass",void 0),e([me()],_n.prototype,"_config",void 0),e([me()],_n.prototype,"_registry",void 0),e([me()],_n.prototype,"_registryError",void 0),e([me()],_n.prototype,"_discovered",void 0),_n=e([he(ve)],_n),window.customCards=window.customCards||[],window.customCards.push({type:ve,name:"Adaptive Cover",description:"Visualize sun/window geometry, the decision trace, and live cover positions with inline controls.",preview:!0,documentationURL:"https://github.com/mrvollger/adaptive-cover-card"}),console.info(`%c adaptive-cover-card %c v${_e} `,"color: white; background: #3f51b5; font-weight: 700;","color: #3f51b5; background: white; font-weight: 700;");export{_n as AdaptiveCoverCard};
