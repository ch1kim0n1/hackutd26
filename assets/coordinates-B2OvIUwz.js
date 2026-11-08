import{i as e}from"./rolldown-runtime-COiEfhsA.js";import{n as t,t as n}from"./jsx-runtime-CSfnZv0S.js";import{A as r,B as i,C as a,D as o,E as s,F as c,G as l,H as u,I as d,K as f,L as p,M as m,O as h,P as g,R as _,S as v,T as y,U as b,V as x,W as S,_ as C,a as w,b as T,c as E,d as D,f as ee,g as te,h as ne,i as re,j as ie,k as ae,l as oe,o as se,p as ce,q as le,r as ue,s as O,u as de,v as fe,w as pe,x as k,y as me,z as A}from"./OrbitControls-DM18MJY2.js";import{t as he}from"./extends-CvVTau-c.js";var j;function ge(){var e;if(j!==void 0)return j;try{let t,n=document.createElement(`canvas`);return j=!!(window.WebGL2RenderingContext&&(t=n.getContext(`webgl2`))),t&&((e=t.getExtension(`WEBGL_lose_context`))==null||e.loseContext()),j}catch{return j=!1}}var _e=parseInt(`187`.replace(/\D+/g,``)),ve=_e>=125?`uv1`:`uv2`,ye=new E,M=new S,be=class extends me{constructor(){super(),this.isLineSegmentsGeometry=!0,this.type=`LineSegmentsGeometry`,this.setIndex([0,2,1,2,3,1,2,4,3,4,5,3,4,6,5,6,7,5]),this.setAttribute(`position`,new te([-1,2,0,1,2,0,-1,1,0,1,1,0,-1,0,0,1,0,0,-1,-1,0,1,-1,0],3)),this.setAttribute(`uv`,new te([-1,2,1,2,-1,1,1,1,-1,-1,1,-1,-1,-2,1,-2],2))}applyMatrix4(e){let t=this.attributes.instanceStart,n=this.attributes.instanceEnd;return t!==void 0&&(t.applyMatrix4(e),n.applyMatrix4(e),t.needsUpdate=!0),this.boundingBox!==null&&this.computeBoundingBox(),this.boundingSphere!==null&&this.computeBoundingSphere(),this}setPositions(e){let t;e instanceof Float32Array?t=e:Array.isArray(e)&&(t=new Float32Array(e));let n=new T(t,6,1);return this.setAttribute(`instanceStart`,new k(n,3,0)),this.setAttribute(`instanceEnd`,new k(n,3,3)),this.computeBoundingBox(),this.computeBoundingSphere(),this}setColors(e,t=3){let n;e instanceof Float32Array?n=e:Array.isArray(e)&&(n=new Float32Array(e));let r=new T(n,t*2,1);return this.setAttribute(`instanceColorStart`,new k(r,t,0)),this.setAttribute(`instanceColorEnd`,new k(r,t,t)),this}fromWireframeGeometry(e){return this.setPositions(e.attributes.position.array),this}fromEdgesGeometry(e){return this.setPositions(e.attributes.position.array),this}fromMesh(e){return this.fromWireframeGeometry(new le(e.geometry)),this}fromLineSegments(e){let t=e.geometry;return this.setPositions(t.attributes.position.array),this}computeBoundingBox(){this.boundingBox===null&&(this.boundingBox=new E);let e=this.attributes.instanceStart,t=this.attributes.instanceEnd;e!==void 0&&t!==void 0&&(this.boundingBox.setFromBufferAttribute(e),ye.setFromBufferAttribute(t),this.boundingBox.union(ye))}computeBoundingSphere(){this.boundingSphere===null&&(this.boundingSphere=new p),this.boundingBox===null&&this.computeBoundingBox();let e=this.attributes.instanceStart,t=this.attributes.instanceEnd;if(e!==void 0&&t!==void 0){let n=this.boundingSphere.center;this.boundingBox.getCenter(n);let r=0;for(let i=0,a=e.count;i<a;i++)M.fromBufferAttribute(e,i),r=Math.max(r,n.distanceToSquared(M)),M.fromBufferAttribute(t,i),r=Math.max(r,n.distanceToSquared(M));this.boundingSphere.radius=Math.sqrt(r),isNaN(this.boundingSphere.radius)&&console.error(`THREE.LineSegmentsGeometry.computeBoundingSphere(): Computed radius is NaN. The instanced position data is likely to have NaN values.`,this)}}toJSON(){}applyMatrix(e){return console.warn(`THREE.LineSegmentsGeometry: applyMatrix() has been renamed to applyMatrix4().`),this.applyMatrix4(e)}},xe=class extends be{constructor(){super(),this.isLineGeometry=!0,this.type=`LineGeometry`}setPositions(e){let t=e.length-3,n=new Float32Array(2*t);for(let r=0;r<t;r+=3)n[2*r]=e[r],n[2*r+1]=e[r+1],n[2*r+2]=e[r+2],n[2*r+3]=e[r+3],n[2*r+4]=e[r+4],n[2*r+5]=e[r+5];return super.setPositions(n),this}setColors(e,t=3){let n=e.length-t,r=new Float32Array(2*n);if(t===3)for(let i=0;i<n;i+=t)r[2*i]=e[i],r[2*i+1]=e[i+1],r[2*i+2]=e[i+2],r[2*i+3]=e[i+3],r[2*i+4]=e[i+4],r[2*i+5]=e[i+5];else for(let i=0;i<n;i+=t)r[2*i]=e[i],r[2*i+1]=e[i+1],r[2*i+2]=e[i+2],r[2*i+3]=e[i+3],r[2*i+4]=e[i+4],r[2*i+5]=e[i+5],r[2*i+6]=e[i+6],r[2*i+7]=e[i+7];return super.setColors(r,t),this}fromLine(e){let t=e.geometry;return this.setPositions(t.attributes.position.array),this}},Se=class extends d{constructor(e){super({type:`LineMaterial`,uniforms:i.clone(i.merge([se.common,se.fog,{worldUnits:{value:1},linewidth:{value:1},resolution:{value:new b(1,1)},dashOffset:{value:0},dashScale:{value:1},dashSize:{value:1},gapSize:{value:1}}])),vertexShader:`
				#include <common>
				#include <fog_pars_vertex>
				#include <logdepthbuf_pars_vertex>
				#include <clipping_planes_pars_vertex>

				uniform float linewidth;
				uniform vec2 resolution;

				attribute vec3 instanceStart;
				attribute vec3 instanceEnd;

				#ifdef USE_COLOR
					#ifdef USE_LINE_COLOR_ALPHA
						varying vec4 vLineColor;
						attribute vec4 instanceColorStart;
						attribute vec4 instanceColorEnd;
					#else
						varying vec3 vLineColor;
						attribute vec3 instanceColorStart;
						attribute vec3 instanceColorEnd;
					#endif
				#endif

				#ifdef WORLD_UNITS

					varying vec4 worldPos;
					varying vec3 worldStart;
					varying vec3 worldEnd;

					#ifdef USE_DASH

						varying vec2 vUv;

					#endif

				#else

					varying vec2 vUv;

				#endif

				#ifdef USE_DASH

					uniform float dashScale;
					attribute float instanceDistanceStart;
					attribute float instanceDistanceEnd;
					varying float vLineDistance;

				#endif

				void trimSegment( const in vec4 start, inout vec4 end ) {

					// trim end segment so it terminates between the camera plane and the near plane

					// conservative estimate of the near plane
					float a = projectionMatrix[ 2 ][ 2 ]; // 3nd entry in 3th column
					float b = projectionMatrix[ 3 ][ 2 ]; // 3nd entry in 4th column
					float nearEstimate = - 0.5 * b / a;

					float alpha = ( nearEstimate - start.z ) / ( end.z - start.z );

					end.xyz = mix( start.xyz, end.xyz, alpha );

				}

				void main() {

					#ifdef USE_COLOR

						vLineColor = ( position.y < 0.5 ) ? instanceColorStart : instanceColorEnd;

					#endif

					#ifdef USE_DASH

						vLineDistance = ( position.y < 0.5 ) ? dashScale * instanceDistanceStart : dashScale * instanceDistanceEnd;
						vUv = uv;

					#endif

					float aspect = resolution.x / resolution.y;

					// camera space
					vec4 start = modelViewMatrix * vec4( instanceStart, 1.0 );
					vec4 end = modelViewMatrix * vec4( instanceEnd, 1.0 );

					#ifdef WORLD_UNITS

						worldStart = start.xyz;
						worldEnd = end.xyz;

					#else

						vUv = uv;

					#endif

					// special case for perspective projection, and segments that terminate either in, or behind, the camera plane
					// clearly the gpu firmware has a way of addressing this issue when projecting into ndc space
					// but we need to perform ndc-space calculations in the shader, so we must address this issue directly
					// perhaps there is a more elegant solution -- WestLangley

					bool perspective = ( projectionMatrix[ 2 ][ 3 ] == - 1.0 ); // 4th entry in the 3rd column

					if ( perspective ) {

						if ( start.z < 0.0 && end.z >= 0.0 ) {

							trimSegment( start, end );

						} else if ( end.z < 0.0 && start.z >= 0.0 ) {

							trimSegment( end, start );

						}

					}

					// clip space
					vec4 clipStart = projectionMatrix * start;
					vec4 clipEnd = projectionMatrix * end;

					// ndc space
					vec3 ndcStart = clipStart.xyz / clipStart.w;
					vec3 ndcEnd = clipEnd.xyz / clipEnd.w;

					// direction
					vec2 dir = ndcEnd.xy - ndcStart.xy;

					// account for clip-space aspect ratio
					dir.x *= aspect;
					dir = normalize( dir );

					#ifdef WORLD_UNITS

						// get the offset direction as perpendicular to the view vector
						vec3 worldDir = normalize( end.xyz - start.xyz );
						vec3 offset;
						if ( position.y < 0.5 ) {

							offset = normalize( cross( start.xyz, worldDir ) );

						} else {

							offset = normalize( cross( end.xyz, worldDir ) );

						}

						// sign flip
						if ( position.x < 0.0 ) offset *= - 1.0;

						float forwardOffset = dot( worldDir, vec3( 0.0, 0.0, 1.0 ) );

						// don't extend the line if we're rendering dashes because we
						// won't be rendering the endcaps
						#ifndef USE_DASH

							// extend the line bounds to encompass  endcaps
							start.xyz += - worldDir * linewidth * 0.5;
							end.xyz += worldDir * linewidth * 0.5;

							// shift the position of the quad so it hugs the forward edge of the line
							offset.xy -= dir * forwardOffset;
							offset.z += 0.5;

						#endif

						// endcaps
						if ( position.y > 1.0 || position.y < 0.0 ) {

							offset.xy += dir * 2.0 * forwardOffset;

						}

						// adjust for linewidth
						offset *= linewidth * 0.5;

						// set the world position
						worldPos = ( position.y < 0.5 ) ? start : end;
						worldPos.xyz += offset;

						// project the worldpos
						vec4 clip = projectionMatrix * worldPos;

						// shift the depth of the projected points so the line
						// segments overlap neatly
						vec3 clipPose = ( position.y < 0.5 ) ? ndcStart : ndcEnd;
						clip.z = clipPose.z * clip.w;

					#else

						vec2 offset = vec2( dir.y, - dir.x );
						// undo aspect ratio adjustment
						dir.x /= aspect;
						offset.x /= aspect;

						// sign flip
						if ( position.x < 0.0 ) offset *= - 1.0;

						// endcaps
						if ( position.y < 0.0 ) {

							offset += - dir;

						} else if ( position.y > 1.0 ) {

							offset += dir;

						}

						// adjust for linewidth
						offset *= linewidth;

						// adjust for clip-space to screen-space conversion // maybe resolution should be based on viewport ...
						offset /= resolution.y;

						// select end
						vec4 clip = ( position.y < 0.5 ) ? clipStart : clipEnd;

						// back to clip space
						offset *= clip.w;

						clip.xy += offset;

					#endif

					gl_Position = clip;

					vec4 mvPosition = ( position.y < 0.5 ) ? start : end; // this is an approximation

					#include <logdepthbuf_vertex>
					#include <clipping_planes_vertex>
					#include <fog_vertex>

				}
			`,fragmentShader:`
				uniform vec3 diffuse;
				uniform float opacity;
				uniform float linewidth;

				#ifdef USE_DASH

					uniform float dashOffset;
					uniform float dashSize;
					uniform float gapSize;

				#endif

				varying float vLineDistance;

				#ifdef WORLD_UNITS

					varying vec4 worldPos;
					varying vec3 worldStart;
					varying vec3 worldEnd;

					#ifdef USE_DASH

						varying vec2 vUv;

					#endif

				#else

					varying vec2 vUv;

				#endif

				#include <common>
				#include <fog_pars_fragment>
				#include <logdepthbuf_pars_fragment>
				#include <clipping_planes_pars_fragment>

				#ifdef USE_COLOR
					#ifdef USE_LINE_COLOR_ALPHA
						varying vec4 vLineColor;
					#else
						varying vec3 vLineColor;
					#endif
				#endif

				vec2 closestLineToLine(vec3 p1, vec3 p2, vec3 p3, vec3 p4) {

					float mua;
					float mub;

					vec3 p13 = p1 - p3;
					vec3 p43 = p4 - p3;

					vec3 p21 = p2 - p1;

					float d1343 = dot( p13, p43 );
					float d4321 = dot( p43, p21 );
					float d1321 = dot( p13, p21 );
					float d4343 = dot( p43, p43 );
					float d2121 = dot( p21, p21 );

					float denom = d2121 * d4343 - d4321 * d4321;

					float numer = d1343 * d4321 - d1321 * d4343;

					mua = numer / denom;
					mua = clamp( mua, 0.0, 1.0 );
					mub = ( d1343 + d4321 * ( mua ) ) / d4343;
					mub = clamp( mub, 0.0, 1.0 );

					return vec2( mua, mub );

				}

				void main() {

					#include <clipping_planes_fragment>

					#ifdef USE_DASH

						if ( vUv.y < - 1.0 || vUv.y > 1.0 ) discard; // discard endcaps

						if ( mod( vLineDistance + dashOffset, dashSize + gapSize ) > dashSize ) discard; // todo - FIX

					#endif

					float alpha = opacity;

					#ifdef WORLD_UNITS

						// Find the closest points on the view ray and the line segment
						vec3 rayEnd = normalize( worldPos.xyz ) * 1e5;
						vec3 lineDir = worldEnd - worldStart;
						vec2 params = closestLineToLine( worldStart, worldEnd, vec3( 0.0, 0.0, 0.0 ), rayEnd );

						vec3 p1 = worldStart + lineDir * params.x;
						vec3 p2 = rayEnd * params.y;
						vec3 delta = p1 - p2;
						float len = length( delta );
						float norm = len / linewidth;

						#ifndef USE_DASH

							#ifdef USE_ALPHA_TO_COVERAGE

								float dnorm = fwidth( norm );
								alpha = 1.0 - smoothstep( 0.5 - dnorm, 0.5 + dnorm, norm );

							#else

								if ( norm > 0.5 ) {

									discard;

								}

							#endif

						#endif

					#else

						#ifdef USE_ALPHA_TO_COVERAGE

							// artifacts appear on some hardware if a derivative is taken within a conditional
							float a = vUv.x;
							float b = ( vUv.y > 0.0 ) ? vUv.y - 1.0 : vUv.y + 1.0;
							float len2 = a * a + b * b;
							float dlen = fwidth( len2 );

							if ( abs( vUv.y ) > 1.0 ) {

								alpha = 1.0 - smoothstep( 1.0 - dlen, 1.0 + dlen, len2 );

							}

						#else

							if ( abs( vUv.y ) > 1.0 ) {

								float a = vUv.x;
								float b = ( vUv.y > 0.0 ) ? vUv.y - 1.0 : vUv.y + 1.0;
								float len2 = a * a + b * b;

								if ( len2 > 1.0 ) discard;

							}

						#endif

					#endif

					vec4 diffuseColor = vec4( diffuse, alpha );
					#ifdef USE_COLOR
						#ifdef USE_LINE_COLOR_ALPHA
							diffuseColor *= vLineColor;
						#else
							diffuseColor.rgb *= vLineColor;
						#endif
					#endif

					#include <logdepthbuf_fragment>

					gl_FragColor = diffuseColor;

					#include <tonemapping_fragment>
					#include <${_e>=154?`colorspace_fragment`:`encodings_fragment`}>
					#include <fog_fragment>
					#include <premultiplied_alpha_fragment>

				}
			`,clipping:!0}),this.isLineMaterial=!0,this.onBeforeCompile=function(){this.transparent?this.defines.USE_LINE_COLOR_ALPHA=`1`:delete this.defines.USE_LINE_COLOR_ALPHA},Object.defineProperties(this,{color:{enumerable:!0,get:function(){return this.uniforms.diffuse.value},set:function(e){this.uniforms.diffuse.value=e}},worldUnits:{enumerable:!0,get:function(){return`WORLD_UNITS`in this.defines},set:function(e){e===!0?this.defines.WORLD_UNITS=``:delete this.defines.WORLD_UNITS}},linewidth:{enumerable:!0,get:function(){return this.uniforms.linewidth.value},set:function(e){this.uniforms.linewidth.value=e}},dashed:{enumerable:!0,get:function(){return`USE_DASH`in this.defines},set(e){!!e!=`USE_DASH`in this.defines&&(this.needsUpdate=!0),e===!0?this.defines.USE_DASH=``:delete this.defines.USE_DASH}},dashScale:{enumerable:!0,get:function(){return this.uniforms.dashScale.value},set:function(e){this.uniforms.dashScale.value=e}},dashSize:{enumerable:!0,get:function(){return this.uniforms.dashSize.value},set:function(e){this.uniforms.dashSize.value=e}},dashOffset:{enumerable:!0,get:function(){return this.uniforms.dashOffset.value},set:function(e){this.uniforms.dashOffset.value=e}},gapSize:{enumerable:!0,get:function(){return this.uniforms.gapSize.value},set:function(e){this.uniforms.gapSize.value=e}},opacity:{enumerable:!0,get:function(){return this.uniforms.opacity.value},set:function(e){this.uniforms.opacity.value=e}},resolution:{enumerable:!0,get:function(){return this.uniforms.resolution.value},set:function(e){this.uniforms.resolution.value.copy(e)}},alphaToCoverage:{enumerable:!0,get:function(){return`USE_ALPHA_TO_COVERAGE`in this.defines},set:function(e){!!e!=`USE_ALPHA_TO_COVERAGE`in this.defines&&(this.needsUpdate=!0),e===!0?(this.defines.USE_ALPHA_TO_COVERAGE=``,this.extensions.derivatives=!0):(delete this.defines.USE_ALPHA_TO_COVERAGE,this.extensions.derivatives=!1)}}}),this.setValues(e)}},N=new l,Ce=new S,we=new S,P=new l,F=new l,I=new l,L=new S,R=new o,z=new v,Te=new S,B=new E,V=new p,H=new l,U,W;function Ee(e,t,n){return H.set(0,0,-t,1).applyMatrix4(e.projectionMatrix),H.multiplyScalar(1/H.w),H.x=W/n.width,H.y=W/n.height,H.applyMatrix4(e.projectionMatrixInverse),H.multiplyScalar(1/H.w),Math.abs(Math.max(H.x,H.y))}function De(e,t){let n=e.matrixWorld,r=e.geometry,i=r.attributes.instanceStart,a=r.attributes.instanceEnd,o=Math.min(r.instanceCount,i.count);for(let r=0,s=o;r<s;r++){z.start.fromBufferAttribute(i,r),z.end.fromBufferAttribute(a,r),z.applyMatrix4(n);let o=new S,s=new S;U.distanceSqToSegment(z.start,z.end,s,o),s.distanceTo(o)<W*.5&&t.push({point:s,pointOnLine:o,distance:U.origin.distanceTo(s),object:e,face:null,faceIndex:r,uv:null,[ve]:null})}}function Oe(e,t,n){let r=t.projectionMatrix,i=e.material.resolution,a=e.matrixWorld,o=e.geometry,c=o.attributes.instanceStart,l=o.attributes.instanceEnd,u=Math.min(o.instanceCount,c.count),d=-t.near;U.at(1,I),I.w=1,I.applyMatrix4(t.matrixWorldInverse),I.applyMatrix4(r),I.multiplyScalar(1/I.w),I.x*=i.x/2,I.y*=i.y/2,I.z=0,L.copy(I),R.multiplyMatrices(t.matrixWorldInverse,a);for(let t=0,o=u;t<o;t++){if(P.fromBufferAttribute(c,t),F.fromBufferAttribute(l,t),P.w=1,F.w=1,P.applyMatrix4(R),F.applyMatrix4(R),P.z>d&&F.z>d)continue;if(P.z>d){let e=P.z-F.z,t=(P.z-d)/e;P.lerp(F,t)}else if(F.z>d){let e=F.z-P.z,t=(F.z-d)/e;F.lerp(P,t)}P.applyMatrix4(r),F.applyMatrix4(r),P.multiplyScalar(1/P.w),F.multiplyScalar(1/F.w),P.x*=i.x/2,P.y*=i.y/2,F.x*=i.x/2,F.y*=i.y/2,z.start.copy(P),z.start.z=0,z.end.copy(F),z.end.z=0;let o=z.closestPointToPointParameter(L,!0);z.at(o,Te);let u=s.lerp(P.z,F.z,o),f=u>=-1&&u<=1,p=L.distanceTo(Te)<W*.5;if(f&&p){z.start.fromBufferAttribute(c,t),z.end.fromBufferAttribute(l,t),z.start.applyMatrix4(a),z.end.applyMatrix4(a);let r=new S,i=new S;U.distanceSqToSegment(z.start,z.end,i,r),n.push({point:i,pointOnLine:r,distance:U.origin.distanceTo(i),object:e,face:null,faceIndex:t,uv:null,[ve]:null})}}}var ke=class extends h{constructor(e=new be,t=new Se({color:Math.random()*16777215})){super(e,t),this.isLineSegments2=!0,this.type=`LineSegments2`}computeLineDistances(){let e=this.geometry,t=e.attributes.instanceStart,n=e.attributes.instanceEnd,r=new Float32Array(2*t.count);for(let e=0,i=0,a=t.count;e<a;e++,i+=2)Ce.fromBufferAttribute(t,e),we.fromBufferAttribute(n,e),r[i]=i===0?0:r[i-1],r[i+1]=r[i]+Ce.distanceTo(we);let i=new T(r,2,1);return e.setAttribute(`instanceDistanceStart`,new k(i,1,0)),e.setAttribute(`instanceDistanceEnd`,new k(i,1,1)),this}raycast(e,t){let n=this.material.worldUnits,r=e.camera;r===null&&!n&&console.error(`LineSegments2: "Raycaster.camera" needs to be set in order to raycast against LineSegments2 while worldUnits is set to false.`);let i=e.params.Line2===void 0?0:e.params.Line2.threshold||0;U=e.ray;let a=this.matrixWorld,o=this.geometry,s=this.material;W=s.linewidth+i,o.boundingSphere===null&&o.computeBoundingSphere(),V.copy(o.boundingSphere).applyMatrix4(a);let c;if(c=n?W*.5:Ee(r,Math.max(r.near,V.distanceToPoint(U.origin)),s.resolution),V.radius+=c,U.intersectsSphere(V)===!1)return;o.boundingBox===null&&o.computeBoundingBox(),B.copy(o.boundingBox).applyMatrix4(a);let l;l=n?W*.5:Ee(r,Math.max(r.near,B.distanceToPoint(U.origin)),s.resolution),B.expandByScalar(l),U.intersectsBox(B)!==!1&&(n?De(this,t):Oe(this,r,t))}onBeforeRender(e){let t=this.material.uniforms;t&&t.resolution&&(e.getViewport(N),this.material.uniforms.resolution.value.set(N.z,N.w))}},Ae=class extends ke{constructor(e=new xe,t=new Se({color:Math.random()*16777215})){super(e,t),this.isLine2=!0,this.type=`Line2`}},G=e(t()),je=G.forwardRef(function({points:e,color:t=16777215,vertexColors:n,linewidth:r,lineWidth:i,segments:a,dashed:o,...s},c){var u;let d=w(e=>e.size),f=G.useMemo(()=>a?new ke:new Ae,[a]),[p]=G.useState(()=>new Se),m=(n==null||(u=n[0])==null?void 0:u.length)===4?4:3,h=G.useMemo(()=>{let r=a?new be:new xe,i=e.map(e=>{let t=Array.isArray(e);return e instanceof S||e instanceof l?[e.x,e.y,e.z]:e instanceof b?[e.x,e.y,0]:t&&e.length===3?[e[0],e[1],e[2]]:t&&e.length===2?[e[0],e[1],0]:e});if(r.setPositions(i.flat()),n){t=16777215;let e=n.map(e=>e instanceof D?e.toArray():e);r.setColors(e.flat(),m)}return r},[e,a,n,m]);return G.useLayoutEffect(()=>{f.computeLineDistances()},[e,f]),G.useLayoutEffect(()=>{o?p.defines.USE_DASH=``:delete p.defines.USE_DASH,p.needsUpdate=!0},[o,p]),G.useEffect(()=>()=>{h.dispose(),p.dispose()},[h]),G.createElement(`primitive`,he({object:f,ref:c},s),G.createElement(`primitive`,{object:h,attach:`geometry`}),G.createElement(`primitive`,he({object:p,attach:`material`,color:t,vertexColors:!!n,resolution:[d.width,d.height],linewidth:r??i??1,dashed:o,transparent:m===4},s)))}),Me=n(),Ne=(()=>{let e=new Float32Array([-1,-1,0,3,-1,0,-1,3,0]),t=new Float32Array([0,0,2,0,0,2]),n=new de;return n.setAttribute(`position`,new oe(e,3)),n.setAttribute(`uv`,new oe(t,2)),n})(),K=class e{static get fullscreenGeometry(){return Ne}constructor(e=`Pass`,t=new c,n=new ie){this.name=e,this.renderer=null,this.scene=t,this.camera=n,this.screen=null,this.rtt=!0,this.needsSwap=!0,this.needsDepthBlit=!1,this.needsDepthTexture=!1,this.enabled=!0}get renderToScreen(){return!this.rtt}set renderToScreen(e){if(this.rtt===e){let t=this.fullscreenMaterial;t!==null&&(t.needsUpdate=!0),this.rtt=!e}}set mainScene(e){}set mainCamera(e){}setRenderer(e){this.renderer=e}isEnabled(){return this.enabled}setEnabled(e){this.enabled=e}get fullscreenMaterial(){return this.screen===null?null:this.screen.material}set fullscreenMaterial(t){let n=this.screen;n===null?(n=new h(e.fullscreenGeometry,t),n.frustumCulled=!1,this.scene===null&&(this.scene=new c),this.scene.add(n),this.screen=n):n.material=t}getFullscreenMaterial(){return this.fullscreenMaterial}setFullscreenMaterial(e){this.fullscreenMaterial=e}getDepthTexture(){return null}setDepthTexture(e,t=O){}render(e,t,n,r,i){throw Error(`Render method not implemented!`)}setSize(e,t){}initialize(e,t,n){}dispose(){for(let t of Object.keys(this)){let n=this[t];(n instanceof f||n instanceof y||n instanceof _||n instanceof e)&&this[t].dispose()}this.fullscreenMaterial!==null&&this.fullscreenMaterial.dispose()}},Pe=class extends K{constructor(){super(`ClearMaskPass`,null,null),this.needsSwap=!1}render(e,t,n,r,i){let a=e.state.buffers.stencil;a.setLocked(!1),a.setTest(!1)}},Fe=`#ifdef COLOR_WRITE
#include <common>
#include <dithering_pars_fragment>
#ifdef FRAMEBUFFER_PRECISION_HIGH
uniform mediump sampler2D inputBuffer;
#else
uniform lowp sampler2D inputBuffer;
#endif
#endif
#ifdef DEPTH_WRITE
#include <packing>
#ifdef GL_FRAGMENT_PRECISION_HIGH
uniform highp sampler2D depthBuffer;
#else
uniform mediump sampler2D depthBuffer;
#endif
float readDepth(const in vec2 uv){
#if DEPTH_PACKING == 3201
return unpackRGBAToDepth(texture2D(depthBuffer,uv));
#else
return texture2D(depthBuffer,uv).r;
#endif
}
#endif
#ifdef USE_WEIGHTS
uniform vec4 channelWeights;
#endif
uniform float opacity;varying vec2 vUv;void main(){
#ifdef COLOR_WRITE
vec4 texel=texture2D(inputBuffer,vUv);
#ifdef USE_WEIGHTS
texel*=channelWeights;
#endif
gl_FragColor=opacity*texel;
#ifdef COLOR_SPACE_CONVERSION
#include <colorspace_fragment>
#endif
#include <dithering_fragment>
#else
gl_FragColor=vec4(0.0);
#endif
#ifdef DEPTH_WRITE
gl_FragDepth=readDepth(vUv);
#endif
}`,Ie=`varying vec2 vUv;void main(){vUv=position.xy*0.5+0.5;gl_Position=vec4(position.xy,1.0,1.0);}`,Le=class extends d{constructor(){super({name:`CopyMaterial`,defines:{COLOR_SPACE_CONVERSION:`1`,DEPTH_PACKING:`0`,COLOR_WRITE:`1`},uniforms:{inputBuffer:new A(null),depthBuffer:new A(null),channelWeights:new A(null),opacity:new A(1)},blending:0,toneMapped:!1,depthWrite:!1,depthTest:!1,fragmentShader:Fe,vertexShader:Ie}),this.depthFunc=1}get inputBuffer(){return this.uniforms.inputBuffer.value}set inputBuffer(e){let t=e!==null;this.colorWrite!==t&&(t?this.defines.COLOR_WRITE=!0:delete this.defines.COLOR_WRITE,this.colorWrite=t,this.needsUpdate=!0),this.uniforms.inputBuffer.value=e}get depthBuffer(){return this.uniforms.depthBuffer.value}set depthBuffer(e){let t=e!==null;this.depthWrite!==t&&(t?this.defines.DEPTH_WRITE=!0:delete this.defines.DEPTH_WRITE,this.depthTest=t,this.depthWrite=t,this.needsUpdate=!0),this.uniforms.depthBuffer.value=e}set depthPacking(e){this.defines.DEPTH_PACKING=e.toFixed(0),this.needsUpdate=!0}get colorSpaceConversion(){return this.defines.COLOR_SPACE_CONVERSION!==void 0}set colorSpaceConversion(e){this.colorSpaceConversion!==e&&(e?this.defines.COLOR_SPACE_CONVERSION=!0:delete this.defines.COLOR_SPACE_CONVERSION,this.needsUpdate=!0)}get channelWeights(){return this.uniforms.channelWeights.value}set channelWeights(e){e===null?delete this.defines.USE_WEIGHTS:(this.defines.USE_WEIGHTS=`1`,this.uniforms.channelWeights.value=e),this.needsUpdate=!0}setInputBuffer(e){this.uniforms.inputBuffer.value=e}getOpacity(e){return this.uniforms.opacity.value}setOpacity(e){this.uniforms.opacity.value=e}},Re=class extends K{constructor(e,t=!0){super(`CopyPass`),this.fullscreenMaterial=new Le,this.needsSwap=!1,this.renderTarget=e,e===void 0&&(this.renderTarget=new f(1,1,{minFilter:a,magFilter:a,stencilBuffer:!1,depthBuffer:!1}),this.renderTarget.texture.name=`CopyPass.Target`),this.autoResize=t}get resize(){return this.autoResize}set resize(e){this.autoResize=e}get texture(){return this.renderTarget.texture}getTexture(){return this.renderTarget.texture}setAutoResizeEnabled(e){this.autoResize=e}render(e,t,n,r,i){this.fullscreenMaterial.inputBuffer=t.texture,e.setRenderTarget(this.renderToScreen?null:this.renderTarget),e.render(this.scene,this.camera)}setSize(e,t){this.autoResize&&this.renderTarget.setSize(e,t)}initialize(e,t,n){n!==void 0&&(this.renderTarget.texture.type=n,n===1009?e!==null&&e.outputColorSpace===`srgb`&&(this.renderTarget.texture.colorSpace=g):this.fullscreenMaterial.defines.FRAMEBUFFER_PRECISION_HIGH=`1`)}},ze=new D,Be=class extends K{constructor(e=!0,t=!0,n=!1){super(`ClearPass`,null,null),this.needsSwap=!1,this.color=e,this.depth=t,this.stencil=n,this.overrideClearColor=null,this.overrideClearAlpha=-1}setClearFlags(e,t,n){this.color=e,this.depth=t,this.stencil=n}getOverrideClearColor(){return this.overrideClearColor}setOverrideClearColor(e){this.overrideClearColor=e}getOverrideClearAlpha(){return this.overrideClearAlpha}setOverrideClearAlpha(e){this.overrideClearAlpha=e}render(e,t,n,r,i){let a=this.overrideClearColor,o=this.overrideClearAlpha,s=e.getClearAlpha(),c=a!==null,l=o>=0;c?(e.getClearColor(ze),e.setClearColor(a,l?o:s)):l&&e.setClearAlpha(o),e.setRenderTarget(this.renderToScreen?null:t),e.clear(this.color,this.depth,this.stencil),c?e.setClearColor(ze,s):l&&e.setClearAlpha(s)}},Ve=class extends K{constructor(e,t){super(`MaskPass`,e,t),this.needsSwap=!1,this.clearPass=new Be(!1,!1,!0),this.inverse=!1}set mainScene(e){this.scene=e}set mainCamera(e){this.camera=e}get inverted(){return this.inverse}set inverted(e){this.inverse=e}get clear(){return this.clearPass.enabled}set clear(e){this.clearPass.enabled=e}getClearPass(){return this.clearPass}isInverted(){return this.inverted}setInverted(e){this.inverted=e}render(e,t,n,r,i){let a=e.getContext(),o=e.state.buffers,s=this.scene,c=this.camera,l=this.clearPass,u=+!this.inverted,d=1-u;o.color.setMask(!1),o.depth.setMask(!1),o.color.setLocked(!0),o.depth.setLocked(!0),o.stencil.setTest(!0),o.stencil.setOp(a.REPLACE,a.REPLACE,a.REPLACE),o.stencil.setFunc(a.ALWAYS,u,4294967295),o.stencil.setClear(d),o.stencil.setLocked(!0),this.clearPass.enabled&&(this.renderToScreen?l.render(e,null):(l.render(e,t),l.render(e,n))),this.renderToScreen?(e.setRenderTarget(null),e.render(s,c)):(e.setRenderTarget(t),e.render(s,c),e.setRenderTarget(n),e.render(s,c)),o.color.setLocked(!1),o.depth.setLocked(!1),o.stencil.setLocked(!1),o.stencil.setFunc(a.EQUAL,1,4294967295),o.stencil.setOp(a.KEEP,a.KEEP,a.KEEP),o.stencil.setLocked(!0)}};function He(e,t){let n=e.getContext();if(t<=0||typeof n.renderbufferStorageMultisample!=`function`)return 0;let r=n.getParameter(n.MAX_SAMPLES),i=Math.min(t,r);if(i<=0)return 0;let a=n.getParameter(n.RENDERBUFFER_BINDING),o=n.createRenderbuffer();try{return n.bindRenderbuffer(n.RENDERBUFFER,o),n.renderbufferStorageMultisample(n.RENDERBUFFER,i,n.RGBA8,1,1),i}catch{return 0}finally{n.bindRenderbuffer(n.RENDERBUFFER,a),n.deleteRenderbuffer(o)}}var Ue=1/1e3,We=1e3,Ge=class{constructor(){this.startTime=performance.now(),this.previousTime=0,this.currentTime=0,this._delta=0,this._elapsed=0,this._fixedDelta=1e3/60,this.timescale=1,this.useFixedDelta=!1,this._autoReset=!1}get autoReset(){return this._autoReset}set autoReset(e){typeof document<`u`&&document.hidden!==void 0&&(e?document.addEventListener(`visibilitychange`,this):document.removeEventListener(`visibilitychange`,this),this._autoReset=e)}get delta(){return this._delta*Ue}get fixedDelta(){return this._fixedDelta*Ue}set fixedDelta(e){this._fixedDelta=e*We}get elapsed(){return this._elapsed*Ue}update(e){this.useFixedDelta?this._delta=this.fixedDelta:(this.previousTime=this.currentTime,this.currentTime=(e===void 0?performance.now():e)-this.startTime,this._delta=this.currentTime-this.previousTime),this._delta*=this.timescale,this._elapsed+=this._delta}reset(){this._delta=0,this._elapsed=0,this.currentTime=performance.now()-this.startTime}getDelta(){return this.delta}getElapsed(){return this.elapsed}handleEvent(e){document.hidden||(this.currentTime=performance.now()-this.startTime)}dispose(){this.autoReset=!1}},Ke=class{constructor(e=null,{depthBuffer:t=!0,stencilBuffer:n=!1,multisampling:r=0,frameBufferType:i=x}={}){this.renderer=null,this.inputBuffer=this.createBuffer(t,n,i,r),this.outputBuffer=this.inputBuffer.clone(),this.copyPass=new Re,this.depthRenderTarget=null,this.passes=[],this.timer=new Ge,this.autoRenderToScreen=!0,this.setRenderer(e)}get stableDepthTexture(){return this.depthRenderTarget===null?null:this.depthRenderTarget.depthTexture}get multisampling(){return this.inputBuffer.samples}set multisampling(e){let t=this.renderer===null?e:He(this.renderer,e);this.multisampling!==t&&(this.inputBuffer.samples=t,this.outputBuffer.samples=t,this.inputBuffer.dispose(),this.outputBuffer.dispose())}getTimer(){return this.timer}getRenderer(){return this.renderer}setRenderer(e){if(this.renderer=e,e!==null){let t=e.getSize(new b),n=e.getContext().getContextAttributes().alpha,r=this.inputBuffer.texture.type;r===1009&&e.outputColorSpace===`srgb`&&(this.inputBuffer.texture.colorSpace=g,this.outputBuffer.texture.colorSpace=g,this.inputBuffer.dispose(),this.outputBuffer.dispose());let i=this.multisampling;this.multisampling=i,e.autoClear=!1,this.setSize(t.width,t.height);for(let t of this.passes)t.initialize(e,n,r)}}replaceRenderer(e,t=!0){let n=this.renderer,r=n.domElement.parentNode;return this.setRenderer(e),t&&r!==null&&(r.removeChild(n.domElement),r.appendChild(e.domElement)),n}createDepthTexture(){let e=new ce;e.name=`EffectComposer.InputDepth`,this.inputBuffer.stencilBuffer?(e.format=ee,e.type=u):e.type=C;let t=new ce;t.format=e.format,t.type=e.type,t.name=`EffectComposer.OutputDepth`;let n=new ce;n.format=e.format,n.type=e.type,n.name=`EffectComposer.StableDepth`,this.inputBuffer.depthTexture=e,this.outputBuffer.depthTexture=t,this.inputBuffer.dispose(),this.outputBuffer.dispose();let{width:r,height:i}=this.inputBuffer;this.depthRenderTarget=new f(r,i,{depthBuffer:!0,stencilBuffer:this.inputBuffer.stencilBuffer,depthTexture:n})}blitDepthBuffer(e){let t=this.renderer,n=this.depthRenderTarget,r=t.properties,i=t.getContext();t.setRenderTarget(n);let a=r.get(e).__webglFramebuffer,o=r.get(n).__webglFramebuffer,s=e.stencilBuffer?i.DEPTH_BUFFER_BIT|i.STENCIL_BUFFER_BIT:i.DEPTH_BUFFER_BIT;i.bindFramebuffer(i.READ_FRAMEBUFFER,a),i.bindFramebuffer(i.DRAW_FRAMEBUFFER,o),i.blitFramebuffer(0,0,e.width,e.height,0,0,n.width,n.height,s,i.NEAREST),i.bindFramebuffer(i.READ_FRAMEBUFFER,null),i.bindFramebuffer(i.DRAW_FRAMEBUFFER,null),t.setRenderTarget(null)}deleteDepthTexture(){let e=this.stableDepthTexture;for(let t of this.passes)t.getDepthTexture()===e&&t.setDepthTexture(null);this.depthRenderTarget!==null&&(this.depthRenderTarget.dispose(),this.depthRenderTarget=null),this.inputBuffer.depthTexture!==null&&(this.inputBuffer.depthTexture.dispose(),this.inputBuffer.depthTexture=null),this.outputBuffer.depthTexture!==null&&(this.outputBuffer.depthTexture.dispose(),this.outputBuffer.depthTexture=null)}createBuffer(e,t,n,r){let i=this.renderer,o=i===null?new b:i.getDrawingBufferSize(new b),s=new f(o.width,o.height,{minFilter:a,magFilter:a,samples:r,stencilBuffer:t,depthBuffer:e,type:n});return n===1009&&i!==null&&i.outputColorSpace===`srgb`&&(s.texture.colorSpace=g),s.texture.name=`EffectComposer.Buffer`,s.texture.generateMipmaps=!1,s}setMainScene(e){for(let t of this.passes)t.mainScene=e}setMainCamera(e){for(let t of this.passes)t.mainCamera=e}addPass(e,t){let n=this.passes,r=this.renderer,i=r.getDrawingBufferSize(new b),a=r.getContext().getContextAttributes().alpha,o=this.inputBuffer.texture.type;if(e.renderer=r,e.setSize(i.width,i.height),e.initialize(r,a,o),this.autoRenderToScreen&&(n.length>0&&(n[n.length-1].renderToScreen=!1),e.renderToScreen&&(this.autoRenderToScreen=!1)),t===void 0?n.push(e):n.splice(t,0,e),this.autoRenderToScreen&&(n[n.length-1].renderToScreen=!0),e.needsDepthTexture||this.depthRenderTarget!==null){if(this.depthRenderTarget===null){this.createDepthTexture();for(let e of n)e.setDepthTexture(this.stableDepthTexture)}else e.setDepthTexture(this.stableDepthTexture)}}removePass(e){let t=this.passes,n=t.indexOf(e);if(n!==-1&&t.splice(n,1).length>0){let r=this.stableDepthTexture;r!==null&&(t.reduce((e,t)=>e||t.needsDepthTexture,!1)||(e.getDepthTexture()===r&&e.setDepthTexture(null),this.deleteDepthTexture())),this.autoRenderToScreen&&n===t.length&&(e.renderToScreen=!1,t.length>0&&(t[t.length-1].renderToScreen=!0))}}removeAllPasses(){let e=this.passes;this.deleteDepthTexture(),e.length>0&&(this.autoRenderToScreen&&(e[e.length-1].renderToScreen=!1),this.passes=[])}render(e){let t=this.renderer,n=this.copyPass,r=this.inputBuffer,i=this.outputBuffer,a,o=!1;e===void 0&&(this.timer.update(),e=this.timer.getDelta());for(let s of this.passes)if(s.enabled){if(s.render(t,r,i,e,o),s.needsDepthBlit&&this.depthRenderTarget!==null&&this.blitDepthBuffer(r),s.needsSwap){if(o){n.renderToScreen=s.renderToScreen;let a=t.getContext(),c=t.state.buffers.stencil;c.setFunc(a.NOTEQUAL,1,4294967295),n.render(t,r,i,e,o),c.setFunc(a.EQUAL,1,4294967295)}a=r,r=i,i=a}s instanceof Ve?o=!0:s instanceof Pe&&(o=!1)}}setSize(e,t,n){let r=this.renderer,i=r.getSize(new b);(e===void 0||t===void 0)&&(e=i.width,t=i.height),(i.width!==e||i.height!==t)&&r.setSize(e,t,n);let a=r.getDrawingBufferSize(new b);this.inputBuffer.setSize(a.width,a.height),this.outputBuffer.setSize(a.width,a.height),this.depthRenderTarget!==null&&this.depthRenderTarget.setSize(a.width,a.height);for(let e of this.passes)e.setSize(a.width,a.height)}reset(){this.dispose(),this.autoRenderToScreen=!0}dispose(){for(let e of this.passes)e.dispose();this.deleteDepthTexture(),this.inputBuffer.dispose(),this.outputBuffer.dispose(),this.copyPass.dispose(),this.timer.dispose(),this.passes=[],K.fullscreenGeometry.dispose()}},q={NONE:0,DEPTH:1,CONVOLUTION:2},J={FRAGMENT_HEAD:`FRAGMENT_HEAD`,FRAGMENT_MAIN_UV:`FRAGMENT_MAIN_UV`,FRAGMENT_MAIN_IMAGE:`FRAGMENT_MAIN_IMAGE`,VERTEX_HEAD:`VERTEX_HEAD`,VERTEX_MAIN_SUPPORT:`VERTEX_MAIN_SUPPORT`},qe=class{constructor(){this.shaderParts=new Map([[J.FRAGMENT_HEAD,null],[J.FRAGMENT_MAIN_UV,null],[J.FRAGMENT_MAIN_IMAGE,null],[J.VERTEX_HEAD,null],[J.VERTEX_MAIN_SUPPORT,null]]),this.defines=new Map,this.uniforms=new Map,this.blendModes=new Map,this.extensions=new Set,this.attributes=q.NONE,this.varyings=new Set,this.uvTransformation=!1,this.readDepth=!1,this.colorSpace=pe}},Je=!1,Ye=class{constructor(e=null){this.originalMaterials=new Map,this.material=null,this.materials=null,this.materialsBackSide=null,this.materialsDoubleSide=null,this.materialsFlatShaded=null,this.materialsFlatShadedBackSide=null,this.materialsFlatShadedDoubleSide=null,this.setMaterial(e),this.meshCount=0,this.replaceMaterial=e=>{if(e.isMesh){let t;if(e.material.flatShading)switch(e.material.side){case 2:t=this.materialsFlatShadedDoubleSide;break;case 1:t=this.materialsFlatShadedBackSide;break;default:t=this.materialsFlatShaded}else switch(e.material.side){case 2:t=this.materialsDoubleSide;break;case 1:t=this.materialsBackSide;break;default:t=this.materials}this.originalMaterials.set(e,e.material),e.material=e.isSkinnedMesh?t[2]:e.isInstancedMesh?t[1]:t[0],++this.meshCount}}}cloneMaterial(e){if(!(e instanceof d))return e.clone();let t=e.uniforms,n=new Map;for(let e in t){let r=t[e].value;r.isRenderTargetTexture&&(t[e].value=null,n.set(e,r))}let r=e.clone();for(let e of n)t[e[0]].value=e[1],r.uniforms[e[0]].value=e[1];return r}setMaterial(e){if(this.disposeMaterials(),this.material=e,e!==null){let t=this.materials=[this.cloneMaterial(e),this.cloneMaterial(e),this.cloneMaterial(e)];for(let n of t)n.uniforms=Object.assign({},e.uniforms),n.side=0;t[2].skinning=!0,this.materialsBackSide=t.map(t=>{let n=this.cloneMaterial(t);return n.uniforms=Object.assign({},e.uniforms),n.side=1,n}),this.materialsDoubleSide=t.map(t=>{let n=this.cloneMaterial(t);return n.uniforms=Object.assign({},e.uniforms),n.side=2,n}),this.materialsFlatShaded=t.map(t=>{let n=this.cloneMaterial(t);return n.uniforms=Object.assign({},e.uniforms),n.flatShading=!0,n}),this.materialsFlatShadedBackSide=t.map(t=>{let n=this.cloneMaterial(t);return n.uniforms=Object.assign({},e.uniforms),n.flatShading=!0,n.side=1,n}),this.materialsFlatShadedDoubleSide=t.map(t=>{let n=this.cloneMaterial(t);return n.uniforms=Object.assign({},e.uniforms),n.flatShading=!0,n.side=2,n})}}render(e,t,n){let r=e.shadowMap.enabled;if(e.shadowMap.enabled=!1,Je){let r=this.originalMaterials;this.meshCount=0,t.traverse(this.replaceMaterial),e.render(t,n);for(let e of r)e[0].material=e[1];this.meshCount!==r.size&&r.clear()}else{let r=t.overrideMaterial;t.overrideMaterial=this.material,e.render(t,n),t.overrideMaterial=r}e.shadowMap.enabled=r}disposeMaterials(){if(this.material!==null){let e=this.materials.concat(this.materialsBackSide).concat(this.materialsDoubleSide).concat(this.materialsFlatShaded).concat(this.materialsFlatShadedBackSide).concat(this.materialsFlatShadedDoubleSide);for(let t of e)t.dispose()}}dispose(){this.originalMaterials.clear(),this.disposeMaterials()}static get workaroundEnabled(){return Je}static set workaroundEnabled(e){Je=e}},Y=-1,X=class extends ne{constructor(e=null,t=Y,n=Y,r=1){super(),e!==null&&this.addEventListener(`change`,()=>e.setSize(this.baseSize.width,this.baseSize.height)),this.baseSize=new b(1,1),this.preferredSize=new b(t,n),this.target=this.preferredSize,this.s=r,this.effectiveSize=new b,this.addEventListener(`change`,()=>this.updateEffectiveSize()),this.updateEffectiveSize()}updateEffectiveSize(){let e=this.baseSize,t=this.preferredSize,n=this.effectiveSize,r=this.scale;n.width=t.width===Y?t.height===Y?Math.round(e.width*r):Math.round(t.height*(e.width/Math.max(e.height,1))):t.width,n.height=t.height===Y?t.width===Y?Math.round(e.height*r):Math.round(t.width/Math.max(e.width/Math.max(e.height,1),1)):t.height}get width(){return this.effectiveSize.width}set width(e){this.preferredWidth=e}get height(){return this.effectiveSize.height}set height(e){this.preferredHeight=e}getWidth(){return this.width}getHeight(){return this.height}get scale(){return this.s}set scale(e){this.s!==e&&(this.s=e,this.preferredSize.setScalar(Y),this.dispatchEvent({type:`change`}))}getScale(){return this.scale}setScale(e){this.scale=e}get baseWidth(){return this.baseSize.width}set baseWidth(e){this.baseSize.width!==e&&(this.baseSize.width=e,this.dispatchEvent({type:`change`}))}getBaseWidth(){return this.baseWidth}setBaseWidth(e){this.baseWidth=e}get baseHeight(){return this.baseSize.height}set baseHeight(e){this.baseSize.height!==e&&(this.baseSize.height=e,this.dispatchEvent({type:`change`}))}getBaseHeight(){return this.baseHeight}setBaseHeight(e){this.baseHeight=e}setBaseSize(e,t){(this.baseSize.width!==e||this.baseSize.height!==t)&&(this.baseSize.set(e,t),this.dispatchEvent({type:`change`}))}get preferredWidth(){return this.preferredSize.width}set preferredWidth(e){this.preferredSize.width!==e&&(this.preferredSize.width=e,this.dispatchEvent({type:`change`}))}getPreferredWidth(){return this.preferredWidth}setPreferredWidth(e){this.preferredWidth=e}get preferredHeight(){return this.preferredSize.height}set preferredHeight(e){this.preferredSize.height!==e&&(this.preferredSize.height=e,this.dispatchEvent({type:`change`}))}getPreferredHeight(){return this.preferredHeight}setPreferredHeight(e){this.preferredHeight=e}setPreferredSize(e,t){(this.preferredSize.width!==e||this.preferredSize.height!==t)&&(this.preferredSize.set(e,t),this.dispatchEvent({type:`change`}))}copy(e){this.s=e.scale,this.baseSize.set(e.baseWidth,e.baseHeight),this.preferredSize.set(e.preferredWidth,e.preferredHeight),this.dispatchEvent({type:`change`})}static get AUTO_SIZE(){return Y}},Z={SKIP:9,SET:30,ADD:0,ALPHA:1,AVERAGE:2,COLOR:3,COLOR_BURN:4,COLOR_DODGE:5,DARKEN:6,DIFFERENCE:7,DIVIDE:8,DST:9,EXCLUSION:10,HARD_LIGHT:11,HARD_MIX:12,HUE:13,INVERT:14,INVERT_RGB:15,LIGHTEN:16,LINEAR_BURN:17,LINEAR_DODGE:18,LINEAR_LIGHT:19,LUMINOSITY:20,MULTIPLY:21,NEGATION:22,NORMAL:23,OVERLAY:24,PIN_LIGHT:25,REFLECT:26,SATURATION:27,SCREEN:28,SOFT_LIGHT:29,SRC:30,SUBTRACT:31,VIVID_LIGHT:32},Xe=new Map([[Z.ADD,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=dst.rgb+src.rgb;return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.ALPHA,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){return mix(dst,src,src.a*opacity);}`],[Z.AVERAGE,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=(dst.rgb+src.rgb)*0.5;return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.COLOR,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 a=RGBToHSL(dst.rgb);vec3 b=RGBToHSL(src.rgb);vec3 c=HSLToRGB(vec3(b.xy,a.z));return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.COLOR_BURN,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 a=dst.rgb,b=src.rgb;vec3 c=mix(step(0.0,b)*(1.0-min(vec3(1.0),(1.0-a)/max(b,1e-9))),vec3(1.0),step(1.0,a));return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.COLOR_DODGE,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 a=dst.rgb,b=src.rgb;vec3 c=step(0.0,a)*mix(min(vec3(1.0),a/max(1.0-b,1e-9)),vec3(1.0),step(1.0,b));return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.DARKEN,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=min(dst.rgb,src.rgb);return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.DIFFERENCE,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=abs(dst.rgb-src.rgb);return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.DIVIDE,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=dst.rgb/max(src.rgb,1e-9);return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.DST,null],[Z.EXCLUSION,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=dst.rgb+src.rgb-2.0*dst.rgb*src.rgb;return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.HARD_LIGHT,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 a=min(dst.rgb,1.0);vec3 b=min(src.rgb,1.0);vec3 c=mix(2.0*a*b,1.0-2.0*(1.0-a)*(1.0-b),step(0.5,b));return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.HARD_MIX,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=step(1.0,dst.rgb+src.rgb);return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.HUE,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 a=RGBToHSL(dst.rgb);vec3 b=RGBToHSL(src.rgb);vec3 c=HSLToRGB(vec3(b.x,a.yz));return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.INVERT,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=max(1.0-src.rgb,0.0);return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.INVERT_RGB,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=src.rgb*max(1.0-dst.rgb,0.0);return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.LIGHTEN,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=max(dst.rgb,src.rgb);return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.LINEAR_BURN,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=clamp(src.rgb+dst.rgb-1.0,0.0,1.0);return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.LINEAR_DODGE,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=min(dst.rgb+src.rgb,1.0);return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.LINEAR_LIGHT,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=clamp(2.0*src.rgb+dst.rgb-1.0,0.0,1.0);return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.LUMINOSITY,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 a=RGBToHSL(dst.rgb);vec3 b=RGBToHSL(src.rgb);vec3 c=HSLToRGB(vec3(a.xy,b.z));return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.MULTIPLY,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=dst.rgb*src.rgb;return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.NEGATION,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=max(1.0-abs(1.0-dst.rgb-src.rgb),0.0);return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.NORMAL,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){return mix(dst,src,opacity);}`],[Z.OVERLAY,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 a=2.0*src.rgb*dst.rgb;vec3 b=1.0-2.0*(1.0-src.rgb)*(1.0-dst.rgb);vec3 c=mix(a,b,step(0.5,dst.rgb));return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.PIN_LIGHT,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 src2=2.0*src.rgb;vec3 c=mix(mix(src2,dst.rgb,step(0.5*dst.rgb,src.rgb)),max(src2-1.0,vec3(0.0)),step(dst.rgb,src2-1.0));return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.REFLECT,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 a=min(dst.rgb*dst.rgb/max(1.0-src.rgb,1e-9),1.0);vec3 c=mix(a,src.rgb,step(1.0,src.rgb));return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.SATURATION,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 a=RGBToHSL(dst.rgb);vec3 b=RGBToHSL(src.rgb);vec3 c=HSLToRGB(vec3(a.x,b.y,a.z));return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.SCREEN,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=dst.rgb+src.rgb-min(dst.rgb*src.rgb,1.0);return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.SOFT_LIGHT,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 src2=2.0*src.rgb;vec3 d=dst.rgb+(src2-1.0);vec3 w=step(0.5,src.rgb);vec3 a=dst.rgb-(1.0-src2)*dst.rgb*(1.0-dst.rgb);vec3 b=mix(d*(sqrt(dst.rgb)-dst.rgb),d*dst.rgb*((16.0*dst.rgb-12.0)*dst.rgb+3.0),w*(1.0-step(0.25,dst.rgb)));vec3 c=mix(a,b,w);return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.SRC,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){return src;}`],[Z.SUBTRACT,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=max(dst.rgb-src.rgb,0.0);return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`],[Z.VIVID_LIGHT,`vec4 blend(const in vec4 dst,const in vec4 src,const in float opacity){vec3 c=mix(max(1.0-min((1.0-dst.rgb)/(2.0*src.rgb),1.0),0.0),min(dst.rgb/(2.0*(1.0-src.rgb)),1.0),step(0.5,src.rgb));return mix(dst,vec4(c,max(dst.a,src.a)),opacity);}`]]),Ze=class extends ne{constructor(e,t=1){super(),this._blendFunction=e,this.opacity=new A(t)}getOpacity(){return this.opacity.value}setOpacity(e){this.opacity.value=e}get blendFunction(){return this._blendFunction}set blendFunction(e){this._blendFunction=e,this.dispatchEvent({type:`change`})}getBlendFunction(){return this.blendFunction}setBlendFunction(e){this.blendFunction=e}getShaderCode(){return Xe.get(this.blendFunction)}},Qe=class extends ne{constructor(e,t,{attributes:n=q.NONE,blendFunction:r=Z.NORMAL,defines:i=new Map,uniforms:a=new Map,extensions:o=null,vertexShader:s=null}={}){super(),this.name=e,this.renderer=null,this.attributes=n,this.fragmentShader=t,this.vertexShader=s,this.defines=i,this.uniforms=a,this.extensions=o,this.blendMode=new Ze(r),this.blendMode.addEventListener(`change`,e=>this.setChanged()),this._inputColorSpace=pe,this._outputColorSpace=``}get inputColorSpace(){return this._inputColorSpace}set inputColorSpace(e){this._inputColorSpace=e,this.setChanged()}get outputColorSpace(){return this._outputColorSpace}set outputColorSpace(e){this._outputColorSpace=e,this.setChanged()}set mainScene(e){}set mainCamera(e){}getName(){return this.name}setRenderer(e){this.renderer=e}getDefines(){return this.defines}getUniforms(){return this.uniforms}getExtensions(){return this.extensions}getBlendMode(){return this.blendMode}getAttributes(){return this.attributes}setAttributes(e){this.attributes=e,this.setChanged()}getFragmentShader(){return this.fragmentShader}setFragmentShader(e){this.fragmentShader=e,this.setChanged()}getVertexShader(){return this.vertexShader}setVertexShader(e){this.vertexShader=e,this.setChanged()}setChanged(){this.dispatchEvent({type:`change`})}setDepthTexture(e,t=O){}update(e,t,n){}setSize(e,t){}initialize(e,t,n){}dispose(){for(let e of Object.keys(this)){let t=this[e];(t instanceof f||t instanceof y||t instanceof _||t instanceof K)&&this[e].dispose()}}},$e={VERY_SMALL:0,SMALL:1,MEDIUM:2,LARGE:3,VERY_LARGE:4,HUGE:5},et=`#ifdef FRAMEBUFFER_PRECISION_HIGH
uniform mediump sampler2D inputBuffer;
#else
uniform lowp sampler2D inputBuffer;
#endif
varying vec2 vUv0;varying vec2 vUv1;varying vec2 vUv2;varying vec2 vUv3;void main(){vec4 sum=texture2D(inputBuffer,vUv0);sum+=texture2D(inputBuffer,vUv1);sum+=texture2D(inputBuffer,vUv2);sum+=texture2D(inputBuffer,vUv3);gl_FragColor=sum*0.25;
#include <colorspace_fragment>
}`,tt=`uniform vec4 texelSize;uniform float kernel;uniform float scale;varying vec2 vUv0;varying vec2 vUv1;varying vec2 vUv2;varying vec2 vUv3;void main(){vec2 uv=position.xy*0.5+0.5;vec2 dUv=(texelSize.xy*vec2(kernel)+texelSize.zw)*scale;vUv0=vec2(uv.x-dUv.x,uv.y+dUv.y);vUv1=vec2(uv.x+dUv.x,uv.y+dUv.y);vUv2=vec2(uv.x+dUv.x,uv.y-dUv.y);vUv3=vec2(uv.x-dUv.x,uv.y-dUv.y);gl_Position=vec4(position.xy,1.0,1.0);}`,nt=[new Float32Array([0,0]),new Float32Array([0,1,1]),new Float32Array([0,1,1,2]),new Float32Array([0,1,2,2,3]),new Float32Array([0,1,2,3,4,4,5]),new Float32Array([0,1,2,3,4,5,7,8,9,10])],rt=class extends d{constructor(e=new l){super({name:`KawaseBlurMaterial`,uniforms:{inputBuffer:new A(null),texelSize:new A(new l),scale:new A(1),kernel:new A(0)},blending:0,toneMapped:!1,depthWrite:!1,depthTest:!1,fragmentShader:et,vertexShader:tt}),this.setTexelSize(e.x,e.y),this.kernelSize=$e.MEDIUM}set inputBuffer(e){this.uniforms.inputBuffer.value=e}setInputBuffer(e){this.inputBuffer=e}get kernelSequence(){return nt[this.kernelSize]}get scale(){return this.uniforms.scale.value}set scale(e){this.uniforms.scale.value=e}getScale(){return this.uniforms.scale.value}setScale(e){this.uniforms.scale.value=e}getKernel(){return null}get kernel(){return this.uniforms.kernel.value}set kernel(e){this.uniforms.kernel.value=e}setKernel(e){this.kernel=e}setTexelSize(e,t){this.uniforms.texelSize.value.set(e,t,e*.5,t*.5)}setSize(e,t){let n=1/e,r=1/t;this.uniforms.texelSize.value.set(n,r,n*.5,r*.5)}},it=class extends K{constructor({kernelSize:e=$e.MEDIUM,resolutionScale:t=.5,width:n=X.AUTO_SIZE,height:r=X.AUTO_SIZE,resolutionX:i=n,resolutionY:a=r}={}){super(`KawaseBlurPass`),this.renderTargetA=new f(1,1,{depthBuffer:!1}),this.renderTargetA.texture.name=`Blur.Target.A`,this.renderTargetB=this.renderTargetA.clone(),this.renderTargetB.texture.name=`Blur.Target.B`;let o=this.resolution=new X(this,i,a,t);o.addEventListener(`change`,e=>this.setSize(o.baseWidth,o.baseHeight)),this._blurMaterial=new rt,this._blurMaterial.kernelSize=e,this.copyMaterial=new Le}getResolution(){return this.resolution}get blurMaterial(){return this._blurMaterial}set blurMaterial(e){this._blurMaterial=e}get dithering(){return this.copyMaterial.dithering}set dithering(e){this.copyMaterial.dithering=e}get kernelSize(){return this.blurMaterial.kernelSize}set kernelSize(e){this.blurMaterial.kernelSize=e}get width(){return this.resolution.width}set width(e){this.resolution.preferredWidth=e}get height(){return this.resolution.height}set height(e){this.resolution.preferredHeight=e}get scale(){return this.blurMaterial.scale}set scale(e){this.blurMaterial.scale=e}getScale(){return this.blurMaterial.scale}setScale(e){this.blurMaterial.scale=e}getKernelSize(){return this.kernelSize}setKernelSize(e){this.kernelSize=e}getResolutionScale(){return this.resolution.scale}setResolutionScale(e){this.resolution.scale=e}render(e,t,n,r,i){let a=this.scene,o=this.camera,s=this.renderTargetA,c=this.renderTargetB,l=this.blurMaterial,u=l.kernelSequence,d=t;this.fullscreenMaterial=l;for(let t=0,n=u.length;t<n;++t){let n=t&1?c:s;l.kernel=u[t],l.inputBuffer=d.texture,e.setRenderTarget(n),e.render(a,o),d=n}this.fullscreenMaterial=this.copyMaterial,this.copyMaterial.inputBuffer=d.texture,e.setRenderTarget(this.renderToScreen?null:n),e.render(a,o)}setSize(e,t){let n=this.resolution;n.setBaseSize(e,t);let r=n.width,i=n.height;this.renderTargetA.setSize(r,i),this.renderTargetB.setSize(r,i),this.blurMaterial.setSize(e,t)}initialize(e,t,n){n!==void 0&&(this.renderTargetA.texture.type=n,this.renderTargetB.texture.type=n,n===1009?e!==null&&e.outputColorSpace===`srgb`&&(this.renderTargetA.texture.colorSpace=g,this.renderTargetB.texture.colorSpace=g):(this.blurMaterial.defines.FRAMEBUFFER_PRECISION_HIGH=`1`,this.copyMaterial.defines.FRAMEBUFFER_PRECISION_HIGH=`1`))}static get AUTO_SIZE(){return X.AUTO_SIZE}},at=`#include <common>
#ifdef FRAMEBUFFER_PRECISION_HIGH
uniform mediump sampler2D inputBuffer;
#else
uniform lowp sampler2D inputBuffer;
#endif
#ifdef RANGE
uniform vec2 range;
#elif defined(THRESHOLD)
uniform float threshold;uniform float smoothing;
#endif
varying vec2 vUv;void main(){vec4 texel=texture2D(inputBuffer,vUv);float l=luminance(texel.rgb);float mask=1.0;
#ifdef RANGE
float low=step(range.x,l);float high=step(l,range.y);mask=low*high;
#elif defined(THRESHOLD)
mask=smoothstep(threshold,threshold+smoothing,l);
#endif
#ifdef COLOR
gl_FragColor=texel*mask;
#else
gl_FragColor=vec4(l*mask);
#endif
}`,ot=class extends d{constructor(e=!1,t=null){super({name:`LuminanceMaterial`,defines:{THREE_REVISION:`187`.replace(/\D+/g,``)},uniforms:{inputBuffer:new A(null),threshold:new A(0),smoothing:new A(1),range:new A(null)},blending:0,toneMapped:!1,depthWrite:!1,depthTest:!1,fragmentShader:at,vertexShader:Ie}),this.colorOutput=e,this.luminanceRange=t}set inputBuffer(e){this.uniforms.inputBuffer.value=e}setInputBuffer(e){this.uniforms.inputBuffer.value=e}get threshold(){return this.uniforms.threshold.value}set threshold(e){this.smoothing>0||e>0?this.defines.THRESHOLD=`1`:delete this.defines.THRESHOLD,this.uniforms.threshold.value=e}getThreshold(){return this.threshold}setThreshold(e){this.threshold=e}get smoothing(){return this.uniforms.smoothing.value}set smoothing(e){this.threshold>0||e>0?this.defines.THRESHOLD=`1`:delete this.defines.THRESHOLD,this.uniforms.smoothing.value=e}getSmoothingFactor(){return this.smoothing}setSmoothingFactor(e){this.smoothing=e}get useThreshold(){return this.threshold>0||this.smoothing>0}set useThreshold(e){}get colorOutput(){return this.defines.COLOR!==void 0}set colorOutput(e){e?this.defines.COLOR=`1`:delete this.defines.COLOR,this.needsUpdate=!0}isColorOutputEnabled(e){return this.colorOutput}setColorOutputEnabled(e){this.colorOutput=e}get useRange(){return this.luminanceRange!==null}set useRange(e){this.luminanceRange=null}get luminanceRange(){return this.uniforms.range.value}set luminanceRange(e){e===null?delete this.defines.RANGE:this.defines.RANGE=`1`,this.uniforms.range.value=e,this.needsUpdate=!0}getLuminanceRange(){return this.luminanceRange}setLuminanceRange(e){this.luminanceRange=e}},st=class extends K{constructor({renderTarget:e,luminanceRange:t,colorOutput:n,resolutionScale:r=1,width:i=X.AUTO_SIZE,height:a=X.AUTO_SIZE,resolutionX:o=i,resolutionY:s=a}={}){super(`LuminancePass`),this.fullscreenMaterial=new ot(n,t),this.needsSwap=!1,this.renderTarget=e,this.renderTarget===void 0&&(this.renderTarget=new f(1,1,{depthBuffer:!1}),this.renderTarget.texture.name=`LuminancePass.Target`);let c=this.resolution=new X(this,o,s,r);c.addEventListener(`change`,e=>this.setSize(c.baseWidth,c.baseHeight))}get texture(){return this.renderTarget.texture}getTexture(){return this.renderTarget.texture}getResolution(){return this.resolution}render(e,t,n,r,i){let a=this.fullscreenMaterial;a.inputBuffer=t.texture,e.setRenderTarget(this.renderToScreen?null:this.renderTarget),e.render(this.scene,this.camera)}setSize(e,t){let n=this.resolution;n.setBaseSize(e,t),this.renderTarget.setSize(n.width,n.height)}initialize(e,t,n){n!==void 0&&n!==1009&&(this.renderTarget.texture.type=n,this.fullscreenMaterial.defines.FRAMEBUFFER_PRECISION_HIGH=`1`)}},ct=`#ifdef FRAMEBUFFER_PRECISION_HIGH
uniform mediump sampler2D inputBuffer;
#else
uniform lowp sampler2D inputBuffer;
#endif
#define WEIGHT_INNER 0.125
#define WEIGHT_OUTER 0.05556
varying vec2 vUv;varying vec2 vUv00;varying vec2 vUv01;varying vec2 vUv02;varying vec2 vUv03;varying vec2 vUv04;varying vec2 vUv05;varying vec2 vUv06;varying vec2 vUv07;varying vec2 vUv08;varying vec2 vUv09;varying vec2 vUv10;varying vec2 vUv11;float clampToBorder(const in vec2 uv){return float(uv.s>=0.0&&uv.s<=1.0&&uv.t>=0.0&&uv.t<=1.0);}void main(){vec4 c=vec4(0.0);vec4 w=WEIGHT_INNER*vec4(clampToBorder(vUv00),clampToBorder(vUv01),clampToBorder(vUv02),clampToBorder(vUv03));c+=w.x*texture2D(inputBuffer,vUv00);c+=w.y*texture2D(inputBuffer,vUv01);c+=w.z*texture2D(inputBuffer,vUv02);c+=w.w*texture2D(inputBuffer,vUv03);w=WEIGHT_OUTER*vec4(clampToBorder(vUv04),clampToBorder(vUv05),clampToBorder(vUv06),clampToBorder(vUv07));c+=w.x*texture2D(inputBuffer,vUv04);c+=w.y*texture2D(inputBuffer,vUv05);c+=w.z*texture2D(inputBuffer,vUv06);c+=w.w*texture2D(inputBuffer,vUv07);w=WEIGHT_OUTER*vec4(clampToBorder(vUv08),clampToBorder(vUv09),clampToBorder(vUv10),clampToBorder(vUv11));c+=w.x*texture2D(inputBuffer,vUv08);c+=w.y*texture2D(inputBuffer,vUv09);c+=w.z*texture2D(inputBuffer,vUv10);c+=w.w*texture2D(inputBuffer,vUv11);c+=WEIGHT_OUTER*texture2D(inputBuffer,vUv);gl_FragColor=c;
#include <colorspace_fragment>
}`,lt=`uniform vec2 texelSize;varying vec2 vUv;varying vec2 vUv00;varying vec2 vUv01;varying vec2 vUv02;varying vec2 vUv03;varying vec2 vUv04;varying vec2 vUv05;varying vec2 vUv06;varying vec2 vUv07;varying vec2 vUv08;varying vec2 vUv09;varying vec2 vUv10;varying vec2 vUv11;void main(){vUv=position.xy*0.5+0.5;vUv00=vUv+texelSize*vec2(-1.0,1.0);vUv01=vUv+texelSize*vec2(1.0,1.0);vUv02=vUv+texelSize*vec2(-1.0,-1.0);vUv03=vUv+texelSize*vec2(1.0,-1.0);vUv04=vUv+texelSize*vec2(-2.0,2.0);vUv05=vUv+texelSize*vec2(0.0,2.0);vUv06=vUv+texelSize*vec2(2.0,2.0);vUv07=vUv+texelSize*vec2(-2.0,0.0);vUv08=vUv+texelSize*vec2(2.0,0.0);vUv09=vUv+texelSize*vec2(-2.0,-2.0);vUv10=vUv+texelSize*vec2(0.0,-2.0);vUv11=vUv+texelSize*vec2(2.0,-2.0);gl_Position=vec4(position.xy,1.0,1.0);}`,ut=class extends d{constructor(){super({name:`DownsamplingMaterial`,uniforms:{inputBuffer:new A(null),texelSize:new A(new b)},blending:0,toneMapped:!1,depthWrite:!1,depthTest:!1,fragmentShader:ct,vertexShader:lt})}set inputBuffer(e){this.uniforms.inputBuffer.value=e}setSize(e,t){this.uniforms.texelSize.value.set(1/e,1/t)}},dt=`#ifdef FRAMEBUFFER_PRECISION_HIGH
uniform mediump sampler2D inputBuffer;uniform mediump sampler2D supportBuffer;
#else
uniform lowp sampler2D inputBuffer;uniform lowp sampler2D supportBuffer;
#endif
uniform float radius;varying vec2 vUv;varying vec2 vUv0;varying vec2 vUv1;varying vec2 vUv2;varying vec2 vUv3;varying vec2 vUv4;varying vec2 vUv5;varying vec2 vUv6;varying vec2 vUv7;void main(){vec4 c=vec4(0.0);c+=texture2D(inputBuffer,vUv0)*0.0625;c+=texture2D(inputBuffer,vUv1)*0.125;c+=texture2D(inputBuffer,vUv2)*0.0625;c+=texture2D(inputBuffer,vUv3)*0.125;c+=texture2D(inputBuffer,vUv)*0.25;c+=texture2D(inputBuffer,vUv4)*0.125;c+=texture2D(inputBuffer,vUv5)*0.0625;c+=texture2D(inputBuffer,vUv6)*0.125;c+=texture2D(inputBuffer,vUv7)*0.0625;vec4 baseColor=texture2D(supportBuffer,vUv);gl_FragColor=mix(baseColor,c,radius);
#include <colorspace_fragment>
}`,ft=`uniform vec2 texelSize;varying vec2 vUv;varying vec2 vUv0;varying vec2 vUv1;varying vec2 vUv2;varying vec2 vUv3;varying vec2 vUv4;varying vec2 vUv5;varying vec2 vUv6;varying vec2 vUv7;void main(){vUv=position.xy*0.5+0.5;vUv0=vUv+texelSize*vec2(-1.0,1.0);vUv1=vUv+texelSize*vec2(0.0,1.0);vUv2=vUv+texelSize*vec2(1.0,1.0);vUv3=vUv+texelSize*vec2(-1.0,0.0);vUv4=vUv+texelSize*vec2(1.0,0.0);vUv5=vUv+texelSize*vec2(-1.0,-1.0);vUv6=vUv+texelSize*vec2(0.0,-1.0);vUv7=vUv+texelSize*vec2(1.0,-1.0);gl_Position=vec4(position.xy,1.0,1.0);}`,pt=class extends d{constructor(){super({name:`UpsamplingMaterial`,uniforms:{inputBuffer:new A(null),supportBuffer:new A(null),texelSize:new A(new b),radius:new A(.85)},blending:0,toneMapped:!1,depthWrite:!1,depthTest:!1,fragmentShader:dt,vertexShader:ft})}set inputBuffer(e){this.uniforms.inputBuffer.value=e}set supportBuffer(e){this.uniforms.supportBuffer.value=e}get radius(){return this.uniforms.radius.value}set radius(e){this.uniforms.radius.value=e}setSize(e,t){this.uniforms.texelSize.value.set(1/e,1/t)}},mt=class extends K{constructor(){super(`MipmapBlurPass`),this.needsSwap=!1,this.renderTarget=new f(1,1,{depthBuffer:!1}),this.renderTarget.texture.name=`Upsampling.Mipmap0`,this.downsamplingMipmaps=[],this.upsamplingMipmaps=[],this.downsamplingMaterial=new ut,this.upsamplingMaterial=new pt,this.resolution=new b}get texture(){return this.renderTarget.texture}get levels(){return this.downsamplingMipmaps.length}set levels(e){if(this.levels!==e){let t=this.renderTarget;this.dispose(),this.downsamplingMipmaps=[],this.upsamplingMipmaps=[];for(let n=0;n<e;++n){let e=t.clone();e.texture.name=`Downsampling.Mipmap`+n,this.downsamplingMipmaps.push(e)}this.upsamplingMipmaps.push(t);for(let n=1,r=e-1;n<r;++n){let e=t.clone();e.texture.name=`Upsampling.Mipmap`+n,this.upsamplingMipmaps.push(e)}this.setSize(this.resolution.x,this.resolution.y)}}get radius(){return this.upsamplingMaterial.radius}set radius(e){this.upsamplingMaterial.radius=e}render(e,t,n,r,i){let{scene:a,camera:o}=this,{downsamplingMaterial:s,upsamplingMaterial:c}=this,{downsamplingMipmaps:l,upsamplingMipmaps:u}=this,d=t;this.fullscreenMaterial=s;for(let t=0,n=l.length;t<n;++t){let n=l[t];s.setSize(d.width,d.height),s.inputBuffer=d.texture,e.setRenderTarget(n),e.render(a,o),d=n}this.fullscreenMaterial=c;for(let t=u.length-1;t>=0;--t){let n=u[t];c.setSize(d.width,d.height),c.inputBuffer=d.texture,c.supportBuffer=l[t].texture,e.setRenderTarget(n),e.render(a,o),d=n}}setSize(e,t){let n=this.resolution;n.set(e,t);let r=n.width,i=n.height;for(let e=0,t=this.downsamplingMipmaps.length;e<t;++e)r=Math.round(r*.5),i=Math.round(i*.5),this.downsamplingMipmaps[e].setSize(r,i),e<this.upsamplingMipmaps.length&&this.upsamplingMipmaps[e].setSize(r,i)}initialize(e,t,n){if(n!==void 0){let t=this.downsamplingMipmaps.concat(this.upsamplingMipmaps);for(let e of t)e.texture.type=n;if(n!==1009)this.downsamplingMaterial.defines.FRAMEBUFFER_PRECISION_HIGH=`1`,this.upsamplingMaterial.defines.FRAMEBUFFER_PRECISION_HIGH=`1`;else if(e!==null&&e.outputColorSpace===`srgb`)for(let e of t)e.texture.colorSpace=g}}dispose(){super.dispose();for(let e of this.downsamplingMipmaps.concat(this.upsamplingMipmaps))e.dispose()}},ht=`#ifdef FRAMEBUFFER_PRECISION_HIGH
uniform mediump sampler2D map;
#else
uniform lowp sampler2D map;
#endif
uniform float intensity;void mainImage(const in vec4 inputColor,const in vec2 uv,out vec4 outputColor){outputColor=texture2D(map,uv)*intensity;}`,gt=class extends Qe{constructor({blendFunction:e=Z.SCREEN,luminanceThreshold:t=1,luminanceSmoothing:n=.03,mipmapBlur:r=!0,intensity:i=1,radius:a=.85,levels:o=8,kernelSize:s=$e.LARGE,resolutionScale:c=.5,width:l=X.AUTO_SIZE,height:u=X.AUTO_SIZE,resolutionX:d=l,resolutionY:p=u}={}){super(`BloomEffect`,ht,{blendFunction:e,uniforms:new Map([[`map`,new A(null)],[`intensity`,new A(i)]])}),this.renderTarget=new f(1,1,{depthBuffer:!1}),this.renderTarget.texture.name=`Bloom.Target`,this.blurPass=new it({kernelSize:s}),this.luminancePass=new st({colorOutput:!0}),this.luminanceMaterial.threshold=t,this.luminanceMaterial.smoothing=n,this.mipmapBlurPass=new mt,this.mipmapBlurPass.enabled=r,this.mipmapBlurPass.radius=a,this.mipmapBlurPass.levels=o,this.uniforms.get(`map`).value=r?this.mipmapBlurPass.texture:this.renderTarget.texture;let m=this.resolution=new X(this,d,p,c);m.addEventListener(`change`,e=>this.setSize(m.baseWidth,m.baseHeight))}get texture(){return this.mipmapBlurPass.enabled?this.mipmapBlurPass.texture:this.renderTarget.texture}getTexture(){return this.texture}getResolution(){return this.resolution}getBlurPass(){return this.blurPass}getLuminancePass(){return this.luminancePass}get luminanceMaterial(){return this.luminancePass.fullscreenMaterial}getLuminanceMaterial(){return this.luminancePass.fullscreenMaterial}get width(){return this.resolution.width}set width(e){this.resolution.preferredWidth=e}get height(){return this.resolution.height}set height(e){this.resolution.preferredHeight=e}get dithering(){return this.blurPass.dithering}set dithering(e){this.blurPass.dithering=e}get kernelSize(){return this.blurPass.kernelSize}set kernelSize(e){this.blurPass.kernelSize=e}get distinction(){return console.warn(this.name,`distinction was removed`),1}set distinction(e){console.warn(this.name,`distinction was removed`)}get intensity(){return this.uniforms.get(`intensity`).value}set intensity(e){this.uniforms.get(`intensity`).value=e}getIntensity(){return this.intensity}setIntensity(e){this.intensity=e}getResolutionScale(){return this.resolution.scale}setResolutionScale(e){this.resolution.scale=e}update(e,t,n){let r=this.renderTarget,i=this.luminancePass;i.enabled?(i.render(e,t),this.mipmapBlurPass.enabled?this.mipmapBlurPass.render(e,i.renderTarget):this.blurPass.render(e,i.renderTarget,r)):this.mipmapBlurPass.enabled?this.mipmapBlurPass.render(e,t):this.blurPass.render(e,t,r)}setSize(e,t){let n=this.resolution;n.setBaseSize(e,t),this.renderTarget.setSize(n.width,n.height),this.blurPass.resolution.copy(n),this.luminancePass.setSize(e,t),this.mipmapBlurPass.setSize(e,t)}initialize(e,t,n){this.blurPass.initialize(e,t,n),this.luminancePass.initialize(e,t,n),this.mipmapBlurPass.initialize(e,t,n),n!==void 0&&(this.renderTarget.texture.type=n,e!==null&&e.outputColorSpace===`srgb`&&(this.renderTarget.texture.colorSpace=g))}},_t=class extends K{constructor(e,t,n=null){super(`RenderPass`,e,t),this.needsSwap=!1,this.needsDepthBlit=!0,this.clearPass=new Be,this.overrideMaterialManager=n===null?null:new Ye(n),this.ignoreBackground=!1,this.skipShadowMapUpdate=!1,this.selection=null}set mainScene(e){this.scene=e}set mainCamera(e){this.camera=e}get renderToScreen(){return super.renderToScreen}set renderToScreen(e){super.renderToScreen=e,this.clearPass.renderToScreen=e}get overrideMaterial(){let e=this.overrideMaterialManager;return e===null?null:e.material}set overrideMaterial(e){let t=this.overrideMaterialManager;e===null?t!==null&&(t.dispose(),this.overrideMaterialManager=null):t===null?this.overrideMaterialManager=new Ye(e):t.setMaterial(e)}getOverrideMaterial(){return this.overrideMaterial}setOverrideMaterial(e){this.overrideMaterial=e}get clear(){return this.clearPass.enabled}set clear(e){this.clearPass.enabled=e}getSelection(){return this.selection}setSelection(e){this.selection=e}isBackgroundDisabled(){return this.ignoreBackground}setBackgroundDisabled(e){this.ignoreBackground=e}isShadowMapDisabled(){return this.skipShadowMapUpdate}setShadowMapDisabled(e){this.skipShadowMapUpdate=e}getClearPass(){return this.clearPass}render(e,t,n,r,i){let a=this.scene,o=this.camera,s=this.selection,c=o.layers.mask,l=a.background,u=e.shadowMap.autoUpdate,d=this.renderToScreen?null:t;s!==null&&o.layers.set(s.getLayer()),this.skipShadowMapUpdate&&(e.shadowMap.autoUpdate=!1),(this.ignoreBackground||this.clearPass.overrideClearColor!==null)&&(a.background=null),this.clearPass.enabled&&this.clearPass.render(e,t),e.setRenderTarget(d),this.overrideMaterialManager===null?e.render(a,o):this.overrideMaterialManager.render(e,a,o),o.layers.mask=c,a.background=l,e.shadowMap.autoUpdate=u}},vt=`#include <packing>
#ifdef GL_FRAGMENT_PRECISION_HIGH
uniform highp sampler2D depthBuffer;
#else
uniform mediump sampler2D depthBuffer;
#endif
#ifdef DOWNSAMPLE_NORMALS
uniform lowp sampler2D normalBuffer;
#endif
varying vec2 vUv0;varying vec2 vUv1;varying vec2 vUv2;varying vec2 vUv3;float readDepth(const in vec2 uv){
#if DEPTH_PACKING == 3201
return unpackRGBAToDepth(texture2D(depthBuffer,uv));
#else
return texture2D(depthBuffer,uv).r;
#endif
}int findBestDepth(const in float samples[4]){float c=(samples[0]+samples[1]+samples[2]+samples[3])*0.25;float distances[4];distances[0]=abs(c-samples[0]);distances[1]=abs(c-samples[1]);distances[2]=abs(c-samples[2]);distances[3]=abs(c-samples[3]);float maxDistance=max(max(distances[0],distances[1]),max(distances[2],distances[3]));int remaining[3];int rejected[3];int i,j,k;for(i=0,j=0,k=0;i<4;++i){if(distances[i]<maxDistance){remaining[j++]=i;}else{rejected[k++]=i;}}for(;j<3;++j){remaining[j]=rejected[--k];}vec3 s=vec3(samples[remaining[0]],samples[remaining[1]],samples[remaining[2]]);c=(s.x+s.y+s.z)/3.0;distances[0]=abs(c-s.x);distances[1]=abs(c-s.y);distances[2]=abs(c-s.z);float minDistance=min(distances[0],min(distances[1],distances[2]));for(i=0;i<3;++i){if(distances[i]==minDistance){break;}}return remaining[i];}void main(){float d[4];d[0]=readDepth(vUv0);d[1]=readDepth(vUv1);d[2]=readDepth(vUv2);d[3]=readDepth(vUv3);int index=findBestDepth(d);
#ifdef DOWNSAMPLE_NORMALS
vec3 n[4];n[0]=texture2D(normalBuffer,vUv0).rgb;n[1]=texture2D(normalBuffer,vUv1).rgb;n[2]=texture2D(normalBuffer,vUv2).rgb;n[3]=texture2D(normalBuffer,vUv3).rgb;
#else
vec3 n[4];n[0]=vec3(0.0);n[1]=vec3(0.0);n[2]=vec3(0.0);n[3]=vec3(0.0);
#endif
gl_FragColor=vec4(n[index],d[index]);}`,yt=`uniform vec2 texelSize;varying vec2 vUv0;varying vec2 vUv1;varying vec2 vUv2;varying vec2 vUv3;void main(){vec2 uv=position.xy*0.5+0.5;vUv0=uv;vUv1=vec2(uv.x,uv.y+texelSize.y);vUv2=vec2(uv.x+texelSize.x,uv.y);vUv3=uv+texelSize;gl_Position=vec4(position.xy,1.0,1.0);}`,bt=class extends d{constructor(){super({name:`DepthDownsamplingMaterial`,defines:{DEPTH_PACKING:`0`},uniforms:{depthBuffer:new A(null),normalBuffer:new A(null),texelSize:new A(new b)},blending:0,toneMapped:!1,depthWrite:!1,depthTest:!1,fragmentShader:vt,vertexShader:yt})}set depthBuffer(e){this.uniforms.depthBuffer.value=e}set depthPacking(e){this.defines.DEPTH_PACKING=e.toFixed(0),this.needsUpdate=!0}setDepthBuffer(e,t=O){this.depthBuffer=e,this.depthPacking=t}set normalBuffer(e){this.uniforms.normalBuffer.value=e,e===null?delete this.defines.DOWNSAMPLE_NORMALS:this.defines.DOWNSAMPLE_NORMALS=`1`,this.needsUpdate=!0}setNormalBuffer(e){this.normalBuffer=e}setTexelSize(e,t){this.uniforms.texelSize.value.set(e,t)}setSize(e,t){this.uniforms.texelSize.value.set(1/e,1/t)}},xt=class extends K{constructor({normalBuffer:e=null,resolutionScale:t=.5,width:n=X.AUTO_SIZE,height:i=X.AUTO_SIZE,resolutionX:a=n,resolutionY:o=i}={}){super(`DepthDownsamplingPass`);let s=new bt;s.normalBuffer=e,this.fullscreenMaterial=s,this.needsDepthTexture=!0,this.needsSwap=!1,this.renderTarget=new f(1,1,{minFilter:r,magFilter:r,depthBuffer:!1,type:C}),this.renderTarget.texture.name=`DepthDownsamplingPass.Target`,this.renderTarget.texture.generateMipmaps=!1;let c=this.resolution=new X(this,a,o,t);c.addEventListener(`change`,e=>this.setSize(c.baseWidth,c.baseHeight))}get texture(){return this.renderTarget.texture}getTexture(){return this.renderTarget.texture}getResolution(){return this.resolution}setDepthTexture(e,t=O){this.fullscreenMaterial.depthBuffer=e,this.fullscreenMaterial.depthPacking=t}render(e,t,n,r,i){e.setRenderTarget(this.renderToScreen?null:this.renderTarget),e.render(this.scene,this.camera)}setSize(e,t){let n=this.resolution;n.setBaseSize(e,t),this.renderTarget.setSize(n.width,n.height),this.fullscreenMaterial.setSize(e,t)}initialize(e,t,n){let r=e.getContext();if(!(r.getExtension(`EXT_color_buffer_float`)||r.getExtension(`EXT_color_buffer_half_float`)))throw Error(`Rendering to float texture is not supported.`)}},St=`#include <common>
#include <packing>
#include <dithering_pars_fragment>
#define packFloatToRGBA(v) packDepthToRGBA(v)
#define unpackRGBAToFloat(v) unpackRGBAToDepth(v)
#ifdef FRAMEBUFFER_PRECISION_HIGH
uniform mediump sampler2D inputBuffer;
#else
uniform lowp sampler2D inputBuffer;
#endif
#if DEPTH_PACKING == 3201
uniform lowp sampler2D depthBuffer;
#elif defined(GL_FRAGMENT_PRECISION_HIGH)
uniform highp sampler2D depthBuffer;
#else
uniform mediump sampler2D depthBuffer;
#endif
uniform vec2 resolution;uniform vec2 texelSize;uniform float cameraNear;uniform float cameraFar;uniform float aspect;uniform float time;varying vec2 vUv;vec4 sRGBToLinear(const in vec4 value){return vec4(mix(pow(value.rgb*0.9478672986+vec3(0.0521327014),vec3(2.4)),value.rgb*0.0773993808,vec3(lessThanEqual(value.rgb,vec3(0.04045)))),value.a);}float readDepth(const in vec2 uv){
#if DEPTH_PACKING == 3201
float depth=unpackRGBAToDepth(texture2D(depthBuffer,uv));
#else
float depth=texture2D(depthBuffer,uv).r;
#endif
#if defined(USE_LOGARITHMIC_DEPTH_BUFFER) || defined(LOG_DEPTH)
float d=pow(2.0,depth*log2(cameraFar+1.0))-1.0;float a=cameraFar/(cameraFar-cameraNear);float b=cameraFar*cameraNear/(cameraNear-cameraFar);depth=a+b/d;
#elif defined(USE_REVERSED_DEPTH_BUFFER)
depth=1.0-depth;
#endif
return depth;}float getViewZ(const in float depth){
#ifdef PERSPECTIVE_CAMERA
return perspectiveDepthToViewZ(depth,cameraNear,cameraFar);
#else
return orthographicDepthToViewZ(depth,cameraNear,cameraFar);
#endif
}vec3 RGBToHCV(const in vec3 RGB){vec4 P=mix(vec4(RGB.bg,-1.0,2.0/3.0),vec4(RGB.gb,0.0,-1.0/3.0),step(RGB.b,RGB.g));vec4 Q=mix(vec4(P.xyw,RGB.r),vec4(RGB.r,P.yzx),step(P.x,RGB.r));float C=Q.x-min(Q.w,Q.y);float H=abs((Q.w-Q.y)/(6.0*C+EPSILON)+Q.z);return vec3(H,C,Q.x);}vec3 RGBToHSL(const in vec3 RGB){vec3 HCV=RGBToHCV(RGB);float L=HCV.z-HCV.y*0.5;float S=HCV.y/(1.0-abs(L*2.0-1.0)+EPSILON);return vec3(HCV.x,S,L);}vec3 HueToRGB(const in float H){float R=abs(H*6.0-3.0)-1.0;float G=2.0-abs(H*6.0-2.0);float B=2.0-abs(H*6.0-4.0);return clamp(vec3(R,G,B),0.0,1.0);}vec3 HSLToRGB(const in vec3 HSL){vec3 RGB=HueToRGB(HSL.x);float C=(1.0-abs(2.0*HSL.z-1.0))*HSL.y;return(RGB-0.5)*C+HSL.z;}FRAGMENT_HEAD void main(){FRAGMENT_MAIN_UV vec4 color0=texture2D(inputBuffer,UV);vec4 color1=vec4(0.0);FRAGMENT_MAIN_IMAGE color0.a=clamp(color0.a,0.0,1.0);gl_FragColor=color0;
#ifdef ENCODE_OUTPUT
#include <colorspace_fragment>
#endif
#include <dithering_fragment>
}`,Ct=`uniform vec2 resolution;uniform vec2 texelSize;uniform float cameraNear;uniform float cameraFar;uniform float aspect;uniform float time;varying vec2 vUv;VERTEX_HEAD void main(){vUv=position.xy*0.5+0.5;VERTEX_MAIN_SUPPORT gl_Position=vec4(position.xy,1.0,1.0);}`,wt=class extends d{constructor(e,t,n,r,i=!1){super({name:`EffectMaterial`,defines:{THREE_REVISION:`187`.replace(/\D+/g,``),DEPTH_PACKING:`0`,ENCODE_OUTPUT:`1`},uniforms:{inputBuffer:new A(null),depthBuffer:new A(null),resolution:new A(new b),texelSize:new A(new b),cameraNear:new A(.3),cameraFar:new A(1e3),aspect:new A(1),time:new A(0)},blending:0,toneMapped:!1,depthWrite:!1,depthTest:!1,dithering:i}),e&&this.setShaderParts(e),t&&this.setDefines(t),n&&this.setUniforms(n),this.copyCameraSettings(r)}set inputBuffer(e){this.uniforms.inputBuffer.value=e}setInputBuffer(e){this.uniforms.inputBuffer.value=e}get depthBuffer(){return this.uniforms.depthBuffer.value}set depthBuffer(e){this.uniforms.depthBuffer.value=e}get depthPacking(){return Number(this.defines.DEPTH_PACKING)}set depthPacking(e){this.defines.DEPTH_PACKING=e.toFixed(0),this.needsUpdate=!0}setDepthBuffer(e,t=O){this.depthBuffer=e,this.depthPacking=t}setShaderData(e){this.setShaderParts(e.shaderParts),this.setDefines(e.defines),this.setUniforms(e.uniforms),this.setExtensions(e.extensions)}setShaderParts(e){return this.fragmentShader=St.replace(J.FRAGMENT_HEAD,e.get(J.FRAGMENT_HEAD)||``).replace(J.FRAGMENT_MAIN_UV,e.get(J.FRAGMENT_MAIN_UV)||``).replace(J.FRAGMENT_MAIN_IMAGE,e.get(J.FRAGMENT_MAIN_IMAGE)||``),this.vertexShader=Ct.replace(J.VERTEX_HEAD,e.get(J.VERTEX_HEAD)||``).replace(J.VERTEX_MAIN_SUPPORT,e.get(J.VERTEX_MAIN_SUPPORT)||``),this.needsUpdate=!0,this}setDefines(e){for(let t of e.entries())this.defines[t[0]]=t[1];return this.needsUpdate=!0,this}setUniforms(e){for(let t of e.entries())this.uniforms[t[0]]=t[1];return this}setExtensions(e){this.extensions={};for(let t of e)this.extensions[t]=!0;return this}get encodeOutput(){return this.defines.ENCODE_OUTPUT!==void 0}set encodeOutput(e){this.encodeOutput!==e&&(e?this.defines.ENCODE_OUTPUT=`1`:delete this.defines.ENCODE_OUTPUT,this.needsUpdate=!0)}isOutputEncodingEnabled(e){return this.encodeOutput}setOutputEncodingEnabled(e){this.encodeOutput=e}get time(){return this.uniforms.time.value}set time(e){this.uniforms.time.value=e}setDeltaTime(e){this.uniforms.time.value+=e}adoptCameraSettings(e){this.copyCameraSettings(e)}copyCameraSettings(e){e&&(this.uniforms.cameraNear.value=e.near,this.uniforms.cameraFar.value=e.far,e instanceof m?this.defines.PERSPECTIVE_CAMERA=`1`:delete this.defines.PERSPECTIVE_CAMERA,this.needsUpdate=!0)}setSize(e,t){let n=this.uniforms;n.resolution.value.set(e,t),n.texelSize.value.set(1/e,1/t),n.aspect.value=e/t}static get Section(){return J}};Number(`187`.replace(/\D+/g,``));var Q=255/256;new Float32Array([Q/256**3,Q/256**2,Q/256,Q]),new Float32Array([Q,Q/256,Q/256**2,1/256**3]);function Tt(e,t,n){for(let r of t){let t=`$1`+e+r.charAt(0).toUpperCase()+r.slice(1),i=RegExp(`([^\\.])(\\b`+r+`\\b)`,`g`);for(let e of n.entries())e[1]!==null&&n.set(e[0],e[1].replace(i,t))}}function Et(e,t,n){let r=t.getFragmentShader(),i=t.getVertexShader(),a=r!==void 0&&/mainImage/.test(r),o=r!==void 0&&/mainUv/.test(r);if(n.attributes|=t.getAttributes(),r===void 0)throw Error(`Missing fragment shader (${t.name})`);if(o&&(n.attributes&q.CONVOLUTION)!==0)throw Error(`Effects that transform UVs are incompatible with convolution effects (${t.name})`);if(!a&&!o)throw Error(`Could not find mainImage or mainUv function (${t.name})`);{let s=/\w+\s+(\w+)\([\w\s,]*\)\s*{/g,c=n.shaderParts,l=c.get(J.FRAGMENT_HEAD)||``,u=c.get(J.FRAGMENT_MAIN_UV)||``,d=c.get(J.FRAGMENT_MAIN_IMAGE)||``,f=c.get(J.VERTEX_HEAD)||``,p=c.get(J.VERTEX_MAIN_SUPPORT)||``,m=new Set,h=new Set;if(o&&(u+=`	${e}MainUv(UV);
`,n.uvTransformation=!0),i!==null&&/mainSupport/.test(i)){let t=/mainSupport *\([\w\s]*?uv\s*?\)/.test(i);p+=`	${e}MainSupport(`,p+=t?`vUv);
`:`);
`;for(let e of i.matchAll(/(?:varying\s+\w+\s+([\S\s]*?);)/g))for(let t of e[1].split(/\s*,\s*/))n.varyings.add(t),m.add(t),h.add(t);for(let e of i.matchAll(s))h.add(e[1])}for(let e of r.matchAll(s))h.add(e[1]);for(let e of t.defines.keys())h.add(e.replace(/\([\w\s,]*\)/g,``));for(let e of t.uniforms.keys())h.add(e);h.delete(`while`),h.delete(`for`),h.delete(`if`),t.uniforms.forEach((t,r)=>n.uniforms.set(e+r.charAt(0).toUpperCase()+r.slice(1),t)),t.defines.forEach((t,r)=>n.defines.set(e+r.charAt(0).toUpperCase()+r.slice(1),t));let g=new Map([[`fragment`,r],[`vertex`,i]]);Tt(e,h,n.defines),Tt(e,h,g),r=g.get(`fragment`),i=g.get(`vertex`);let _=t.blendMode;if(n.blendModes.set(_.blendFunction,_),a){t.inputColorSpace!==null&&t.inputColorSpace!==n.colorSpace&&(d+=t.inputColorSpace===`srgb`?`color0 = sRGBTransferOETF(color0);
	`:`color0 = sRGBToLinear(color0);
	`),t.outputColorSpace===``?t.inputColorSpace!==null&&(n.colorSpace=t.inputColorSpace):n.colorSpace=t.outputColorSpace,d+=`${e}MainImage(color0, UV, `,(n.attributes&q.DEPTH)!==0&&/MainImage *\([\w\s,]*?depth[\w\s,]*?\)/.test(r)&&(d+=`depth, `,n.readDepth=!0),d+=`color1);
	`;let i=e+`BlendOpacity`;n.uniforms.set(i,_.opacity),d+=`color0 = blend${_.blendFunction}(color0, color1, ${i});

	`,l+=`uniform float ${i};

`}if(l+=r+`
`,i!==null&&(f+=i+`
`),c.set(J.FRAGMENT_HEAD,l),c.set(J.FRAGMENT_MAIN_UV,u),c.set(J.FRAGMENT_MAIN_IMAGE,d),c.set(J.VERTEX_HEAD,f),c.set(J.VERTEX_MAIN_SUPPORT,p),t.extensions!==null)for(let e of t.extensions)n.extensions.add(e)}}var Dt=class extends K{constructor(e,...t){super(`EffectPass`),this.fullscreenMaterial=new wt(null,null,null,e),this.listener=e=>this.handleEvent(e),this.effects=[],this.setEffects(t),this.skipRendering=!1,this.minTime=1,this.maxTime=1/0,this.timeScale=1}set mainScene(e){for(let t of this.effects)t.mainScene=e}set mainCamera(e){this.fullscreenMaterial.copyCameraSettings(e);for(let t of this.effects)t.mainCamera=e}get encodeOutput(){return this.fullscreenMaterial.encodeOutput}set encodeOutput(e){this.fullscreenMaterial.encodeOutput=e}get dithering(){return this.fullscreenMaterial.dithering}set dithering(e){let t=this.fullscreenMaterial;t.dithering=e,t.needsUpdate=!0}setEffects(e){for(let e of this.effects)e.removeEventListener(`change`,this.listener);this.effects=e.sort((e,t)=>t.attributes-e.attributes);for(let e of this.effects)e.addEventListener(`change`,this.listener)}updateMaterial(){let e=new qe,t=0;for(let n of this.effects)if(n.blendMode.blendFunction===Z.DST)e.attributes|=n.getAttributes()&q.DEPTH;else if((e.attributes&n.getAttributes()&q.CONVOLUTION)!==0)throw Error(`Convolution effects cannot be merged (${n.name})`);else Et(`e`+t++,n,e);let n=e.shaderParts.get(J.FRAGMENT_HEAD),r=e.shaderParts.get(J.FRAGMENT_MAIN_IMAGE),i=e.shaderParts.get(J.FRAGMENT_MAIN_UV),a=/\bblend\b/g;for(let t of e.blendModes.values())n+=t.getShaderCode().replace(a,`blend${t.blendFunction}`)+`
`;(e.attributes&q.DEPTH)===0?this.needsDepthTexture=!1:(e.readDepth&&(r=`float depth = readDepth(UV);

	`+r),this.needsDepthTexture=this.getDepthTexture()===null),e.colorSpace===`srgb`&&(r+=`color0 = sRGBToLinear(color0);
	`),e.uvTransformation?(i=`vec2 transformedUv = vUv;
`+i,e.defines.set(`UV`,`transformedUv`)):e.defines.set(`UV`,`vUv`),e.shaderParts.set(J.FRAGMENT_HEAD,n),e.shaderParts.set(J.FRAGMENT_MAIN_IMAGE,r),e.shaderParts.set(J.FRAGMENT_MAIN_UV,i);for(let[t,n]of e.shaderParts)n!==null&&e.shaderParts.set(t,n.trim().replace(/^#/,`
#`));this.skipRendering=t===0,this.needsSwap=!this.skipRendering,this.fullscreenMaterial.setShaderData(e)}recompile(){this.updateMaterial()}getDepthTexture(){return this.fullscreenMaterial.depthBuffer}setDepthTexture(e,t=O){this.fullscreenMaterial.depthBuffer=e,this.fullscreenMaterial.depthPacking=t;for(let n of this.effects)n.setDepthTexture(e,t)}render(e,t,n,r,i){for(let n of this.effects)n.update(e,t,r);if(!this.skipRendering||this.renderToScreen){let i=this.fullscreenMaterial;i.inputBuffer=t.texture,i.time+=r*this.timeScale,e.setRenderTarget(this.renderToScreen?null:n),e.render(this.scene,this.camera)}}setSize(e,t){this.fullscreenMaterial.setSize(e,t);for(let n of this.effects)n.setSize(e,t)}initialize(e,t,n){this.renderer=e;for(let r of this.effects)r.initialize(e,t,n);this.updateMaterial(),n!==void 0&&n!==1009&&(this.fullscreenMaterial.defines.FRAMEBUFFER_PRECISION_HIGH=`1`)}dispose(){super.dispose();for(let e of this.effects)e.removeEventListener(`change`,this.listener),e.dispose()}handleEvent(e){e.type===`change`&&this.recompile()}},Ot=class extends K{constructor(e,t,{renderTarget:n,resolutionScale:i=1,width:a=X.AUTO_SIZE,height:o=X.AUTO_SIZE,resolutionX:s=a,resolutionY:c=o}={}){super(`NormalPass`),this.needsSwap=!1,this.renderPass=new _t(e,t,new ae);let l=this.renderPass;l.ignoreBackground=!0,l.skipShadowMapUpdate=!0;let u=l.getClearPass();u.overrideClearColor=new D(7829503),u.overrideClearAlpha=1,this.renderTarget=n,this.renderTarget===void 0&&(this.renderTarget=new f(1,1,{minFilter:r,magFilter:r}),this.renderTarget.texture.name=`NormalPass.Target`);let d=this.resolution=new X(this,s,c,i);d.addEventListener(`change`,e=>this.setSize(d.baseWidth,d.baseHeight))}set mainScene(e){this.renderPass.mainScene=e}set mainCamera(e){this.renderPass.mainCamera=e}get texture(){return this.renderTarget.texture}getTexture(){return this.renderTarget.texture}getResolution(){return this.resolution}getResolutionScale(){return this.resolution.scale}setResolutionScale(e){this.resolution.scale=e}render(e,t,n,r,i){let a=this.renderToScreen?null:this.renderTarget;this.renderPass.render(e,a,a)}setSize(e,t){let n=this.resolution;n.setBaseSize(e,t),this.renderTarget.setSize(n.width,n.height)}};new Float32Array([0,0,0]),new Float32Array([1,0,0]),new Float32Array([1,1,0]),new Float32Array([1,1,1]),new Float32Array([0,0,0]),new Float32Array([1,0,0]),new Float32Array([1,0,1]),new Float32Array([1,1,1]),new Float32Array([0,0,0]),new Float32Array([0,0,1]),new Float32Array([1,0,1]),new Float32Array([1,1,1]),new Float32Array([0,0,0]),new Float32Array([0,1,0]),new Float32Array([1,1,0]),new Float32Array([1,1,1]),new Float32Array([0,0,0]),new Float32Array([0,1,0]),new Float32Array([0,1,1]),new Float32Array([1,1,1]),new Float32Array([0,0,0]),new Float32Array([0,0,1]),new Float32Array([0,1,1]),new Float32Array([1,1,1]),new Float32Array([0,-.25,.25,-.125,.125,-.375,.375]),new Float32Array([0,0]),new Float32Array([.25,-.25]),new Float32Array([-.25,.25]),new Float32Array([.125,-.125]),new Float32Array([-.125,.125]),new Uint8Array([0,0]),new Uint8Array([3,0]),new Uint8Array([0,3]),new Uint8Array([3,3]),new Uint8Array([1,0]),new Uint8Array([4,0]),new Uint8Array([1,3]),new Uint8Array([4,3]),new Uint8Array([0,1]),new Uint8Array([3,1]),new Uint8Array([0,4]),new Uint8Array([3,4]),new Uint8Array([1,1]),new Uint8Array([4,1]),new Uint8Array([1,4]),new Uint8Array([4,4]),new Uint8Array([0,0]),new Uint8Array([1,0]),new Uint8Array([0,2]),new Uint8Array([1,2]),new Uint8Array([2,0]),new Uint8Array([3,0]),new Uint8Array([2,2]),new Uint8Array([3,2]),new Uint8Array([0,1]),new Uint8Array([1,1]),new Uint8Array([0,3]),new Uint8Array([1,3]),new Uint8Array([2,1]),new Uint8Array([3,1]),new Uint8Array([2,3]),new Uint8Array([3,3]),$(0,0,0,0),new Float32Array([0,0,0,0]),$(0,0,0,1),new Float32Array([0,0,0,1]),$(0,0,1,0),new Float32Array([0,0,1,0]),$(0,0,1,1),new Float32Array([0,0,1,1]),$(0,1,0,0),new Float32Array([0,1,0,0]),$(0,1,0,1),new Float32Array([0,1,0,1]),$(0,1,1,0),new Float32Array([0,1,1,0]),$(0,1,1,1),new Float32Array([0,1,1,1]),$(1,0,0,0),new Float32Array([1,0,0,0]),$(1,0,0,1),new Float32Array([1,0,0,1]),$(1,0,1,0),new Float32Array([1,0,1,0]),$(1,0,1,1),new Float32Array([1,0,1,1]),$(1,1,0,0),new Float32Array([1,1,0,0]),$(1,1,0,1),new Float32Array([1,1,0,1]),$(1,1,1,0),new Float32Array([1,1,1,0]),$(1,1,1,1),new Float32Array([1,1,1,1]);function kt(e,t,n){return e+(t-e)*n}function $(e,t,n,r){return kt(kt(e,t,.75),kt(n,r,.75),.875)}var At=(0,G.createContext)(null),jt=e=>(e.getAttributes()&q.CONVOLUTION)===q.CONVOLUTION,Mt=G.memo((0,G.forwardRef)(({children:e,camera:t,scene:n,resolutionScale:r,enabled:i=!0,renderPriority:a=1,autoClear:o=!0,depthBuffer:s,enableNormalPass:c,stencilBuffer:l,multisampling:u=8,frameBufferType:d=fe},f)=>{let{gl:p,scene:m,camera:h,size:g}=w(),_=n||m,v=t||h,[y,b,x]=(0,G.useMemo)(()=>{let e=ge(),t=new Ke(p,{depthBuffer:s,stencilBuffer:l,multisampling:u>0&&e?u:0,frameBufferType:d});t.addPass(new _t(_,v));let n=null,i=null;return c&&(i=new Ot(_,v),i.enabled=!1,t.addPass(i),r!==void 0&&e&&(n=new xt({normalBuffer:i.texture,resolutionScale:r}),n.enabled=!1,t.addPass(n))),[t,i,n]},[v,p,s,l,u,d,_,c,r]);(0,G.useEffect)(()=>y?.setSize(g.width,g.height),[y,g]),re((e,t)=>{if(i){let e=p.autoClear;p.autoClear=o,l&&!o&&p.clearStencil(),y.render(t),p.autoClear=e}},i?a:0);let S=(0,G.useRef)(null);(0,G.useLayoutEffect)(()=>{let e=[],t=S.current?.__r3f;if(t&&y){let n=t.objects;for(let t=0;t<n.length;t++){let r=n[t];if(r instanceof Qe){let i=[r];if(!jt(r)){let e=null;for(;(e=n[t+1])instanceof Qe&&!jt(e);)i.push(e),t++}let a=new Dt(v,...i);e.push(a)}else r instanceof K&&e.push(r)}for(let t of e)y?.addPass(t);b&&(b.enabled=!0),x&&(x.enabled=!0)}return()=>{for(let t of e)y?.removePass(t);b&&(b.enabled=!1),x&&(x.enabled=!1)}},[y,e,v,b,x]),(0,G.useEffect)(()=>{let e=p.toneMapping;return p.toneMapping=0,()=>{p.toneMapping=e}},[p]);let C=(0,G.useMemo)(()=>({composer:y,normalPass:b,downSamplingPass:x,resolutionScale:r,camera:v,scene:_}),[y,b,x,r,v,_]);return(0,G.useImperativeHandle)(f,()=>y,[y]),(0,Me.jsx)(At.Provider,{value:C,children:(0,Me.jsx)(`group`,{ref:S,children:e})})})),Nt=0,Pt=new WeakMap,Ft=((e,t)=>G.forwardRef(function({blendFunction:n=t?.blendFunction,opacity:r=t?.opacity,...i},a){let o=Pt.get(e);if(!o){let t=`@react-three/postprocessing/${e.name}-${Nt++}`;ue({[t]:e}),Pt.set(e,o=t)}let s=w(e=>e.camera),c=G.useMemo(()=>[...t?.args??[],...i.args??[{...t,...i}]],[JSON.stringify(i)]);return(0,Me.jsx)(o,{camera:s,"blendMode-blendFunction":n,"blendMode-opacity-value":r,...i,ref:a,args:c})}))(gt,{blendFunction:Z.ADD}),It={origin:{x:0,y:0},metersPerUnit:1};function Lt(e,...t){if(![e.origin.x,e.origin.y,e.metersPerUnit,...t].every(Number.isFinite)||e.metersPerUnit<=0)throw Error(`Coordinates must be finite and metersPerUnit must be positive`)}function Rt(e,t=0,n=It){return Lt(n,e.x,e.y,t),[(e.x-n.origin.x)*n.metersPerUnit,t,-(e.y-n.origin.y)*n.metersPerUnit]}function zt(e,t,n=2,r=.06,i=It){Lt(i,e.x,e.y,t.x,t.y,n,r);let a=Math.hypot(t.x-e.x,t.y-e.y)*i.metersPerUnit;if(a===0||n<=0||r<=0)throw Error(`Wall dimensions must be positive`);return{position:Rt({x:(e.x+t.x)/2,y:(e.y+t.y)/2},n/2,i),size:[a,n,r],rotation:[0,Math.atan2(t.y-e.y,t.x-e.x),0]}}export{je as a,Mt as i,zt as n,Ft as r,Rt as t};